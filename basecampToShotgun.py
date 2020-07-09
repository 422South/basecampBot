import datetime
import os, re, sys
from flask import Flask, request
import requests
from re import search, IGNORECASE
import shotgun_api3 as sg3
import pprint

SCRIPT_KEY = os.environ.get('SG_KEY')
SCRIPT_NAME = os.environ.get('SG_NAME')
SITE_URL = os.environ.get('SG_HOST') + '/api/v1'
sg = sg3.Shotgun(os.environ.get('SG_HOST'), SCRIPT_NAME, SCRIPT_KEY)

app = Flask(__name__)

write_directory = 'BasecampDownloads/'


@app.route("/", methods=['GET', 'POST'])
def defaultLocalHost():
    return "<h1>This is a blank page..." + "</h1>"


def get_auth_header():
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    params = {
        'client_id': SCRIPT_NAME,
        'client_secret': SCRIPT_KEY,
        'grant_type': 'client_credentials',
        'session_uuid': request.form.get('session_uuid')
    }
    resp = requests.post(SITE_URL + '/auth/access_token', headers=headers, params=params)
    pprint.pprint(resp)
    return {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + resp.json()['access_token']
    }

"""

"""


@app.route("/basecamp/updateall", methods=['GET', 'POST'])
def updateAllThreads():
    notes = sg.find('Note', [['sg_basecamptopic', 'is_not', '']], ['sg_basecamptopic', 'sg_latestpostid', 'note_links'])
    for note in notes:
        latestID = note['sg_latestpostid']
        assetID = note['note_links'][0].get("id")
        basecamptopic = note['sg_basecamptopic']

        createNote(latestID, basecamptopic, assetID)

    return "<h1>Threads updated " + "</h1>"


@app.route("/basecamp/confirm", methods=['GET', 'POST'])
def confirm():
    basecamptopic = request.args.get('topic')
    assetID = request.args.get('assetid')

    createNote(0, basecamptopic, int(assetID))

    return "<h1>Upload Successful!</h1>"


def createNote(latestPostID, baseCampTopic, assetId):

    asset = sg.find_one('Asset', [['id', 'is', assetId]], ['id'])

    baseCampTopic = re.sub(r'^.*?---', '', baseCampTopic)
    baseCampTopic = baseCampTopic.replace(' ', '_').replace('/', '_')

    basecampJSON, drainProject, writeDirectory = getBasecampFiles(latestPostID, baseCampTopic)

    # theProjectID = sg.find_one('Project', [['name', 'is', drainProject]], ['id'])
    theProjectID = 289

    # Find all users on the project
    userList = []
    project = sg.find("HumanUser", [["projects", "is", {'type': 'Project', "id": theProjectID}]], ["name"])
    for user in project:
        userList.append(user)

    # If the basecamp thread doesn't exist create it
    baseCampThread = sg.find_one('Note', [['subject', 'is', 'Basecamp Thread for ' + baseCampTopic]], ['name'])
    if baseCampThread == None:
        note_data = {
            'project': {'type': 'Project', 'id': theProjectID},
            'subject': 'Basecamp Thread for ' + baseCampTopic,
            'content': 'Everything from basecamp for this project',
            'sg_basecamptopic': baseCampTopic,
            'sg_latestpostid': '0',
            'note_links': [{'type': 'Asset', 'id': asset['id']}],
            # 'addressings_to': userList,
            'suppress_email_notif': True,
        }
        sg.create('Note', note_data)

    # Build replies onto the new note or add to it if it already exists
    baseCampThread = sg.find_one('Note', [['subject', 'is', 'Basecamp Thread for ' + baseCampTopic]], ['name'])
    for i in basecampJSON:

        if i[0] > latestPostID:
            latestPostID = i[0]

        if i[2] != None:
            theContents = i[2].replace('<br>', '\n') \
                .replace('<p>', '') \
                .replace('</p>', '') \
                .replace('<ul>', '') \
                .replace('</ul>', '') \
                .replace('<div>', '') \
                .replace('</div', '') \
                .replace('<li>', '') \
                .replace('</li>', '') \
                .replace('<a href=', '') \
                .replace('</a>', '') \
                .replace('<b>', '') \
                .replace('</b>', '') \
                .replace('&lt;', '<') \
                .replace('&gt;', '>')
        else:
            theContents = ""

        botUser = sg.find_one('ClientUser', [['name', 'is', 'Basecamp Bot']], ['name'])
        replyDateCreation = 'This note was created by ' + i[1] + ' on ' + i[4].replace('T', ' ').replace('.000Z', '') + '\n\n'
        reply_data = {
            'entity': baseCampThread,
            'content': replyDateCreation + '' + theContents,
            'user': botUser
        }
        sg.create('Reply', reply_data)

        for j in i[3]:
            res = {key: j[key] for key in j.keys() and {'name'}}
            k = res.values()
            imageLocation = writeDirectory + '/' + str(k[0])
            sg.upload('Note', baseCampThread['id'], imageLocation)

    # update the threads post ID
    postIDData = {
        'sg_latestpostid': str(latestPostID),
    }
    sg.update('Note', baseCampThread['id'], postIDData)

    return


@app.route("/basecamp/initiate", methods=['GET', 'POST'])
def process_ami():
    # pprint.pprint(request.form)
    auth_header = get_auth_header()

    # pprint.pprint(auth_header)
    for asset_id in [int(i) for i in request.form.get('selected_ids').split(',')]:
        filters = [['id', 'is', asset_id]]
        assets = sg.find_one('Asset', filters, ['name', 'code', 'description', 'tasks', 'sg_asset_type', 'project', 'notes'])
        assetName = assets['code']
        print("Asset is " + assetName)
        latestPostID = 0
        baseCampTopic = ""
        found = False
        for note in assets['notes']:
            note_specific = sg.find_one('Note', [["id", "is", note['id']]], ['sg_basecamptopic', 'sg_latestpostid'])
            if note_specific['sg_basecamptopic'] != None:
                found = True
                if note_specific['sg_latestpostid'] > latestPostID:
                    latestPostID = note_specific['sg_latestpostid']
                    baseCampTopic = note_specific['sg_basecamptopic']
                    createNote(latestPostID, baseCampTopic, asset_id)

        if not found:
            '''
                Need to ask the user what the baseCampTopic is to continue
            '''

            # print "Loading UI"
            htmlTmp = ""

            url = 'https://basecamp.com/2978927/api/v1/projects.json'
            headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
            auth_422 = ('craig@422south.com', 'Millenium2')
            r = requests.get(url, headers=headers_422, auth=auth_422)
            for basecampProject in r.json():
                if search('^drain', basecampProject['name'], IGNORECASE):
                    topic_url = 'https://basecamp.com/2978927/api/v1/projects/' + str(basecampProject['id']) + '/topics.json'
                    t = requests.get(topic_url, headers=headers_422, auth=auth_422)
                    topics = t.json()
                    for topic in topics:
                        temp = basecampProject['name'] + '---' + str(topic['title'])
                        htmlTmp = htmlTmp + '<option value="' + temp + '">' + temp + '</option>'

            return '<form action="/basecamp/confirm">' \
                   '<select name="topic" size="number_of_options">' \
                   + htmlTmp + \
                   '</select>' \
                   '<input type="submit" value="Confirm">' \
                   '<input type="hidden" id="assetid" name="assetid" value="' + str(asset_id) + '" >' \
                   '</form>'


def getBasecampFiles(latestPostID, baseCampTopic):
    url = 'https://basecamp.com/2978927/api/v1/projects.json'
    headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
    auth_422 = ('craig@422south.com', 'Millenium2')
    r = requests.get(url, headers=headers_422, auth=auth_422)
    basecampName = ""
    usefulData = []
    # pprint.pprint(r.json(), indent= 5)
    for basecampProject in r.json():
        if search('^drain', basecampProject['name'], IGNORECASE):
            # pprint.pprint(basecampProject['name'])
            topic_url = 'https://basecamp.com/2978927/api/v1/projects/' + str(basecampProject['id']) + '/topics.json'
            # print(topic_url)
            t = requests.get(topic_url, headers=headers_422, auth=auth_422)
            topics = t.json()
            # pprint.pprint(topics)
            for topicName in topics:
                # pprint.pprint(topicName)
                # print(topicName['title'], topicName['topicable']['url'])
                topic_title = topicName['title']

                # Only pull down the topic that is relevant
                tmp = topic_title.replace(' ', '_').replace('/', '_')
                if tmp == baseCampTopic:
                    basecampName = str(basecampProject['name']).replace(' ', '_').replace('/', '_')
                    message_url = topicName['topicable']['url']
                    m = requests.get(message_url, headers=headers_422, auth=auth_422)
                    messages = m.json()
                    # for mm in messages:
                    #     pprint.pprint(mm)
                    # pprint.pprint(messages['comments'])
                    comments = messages['comments']

                    if len(comments) > 0:
                        if os.path.exists(write_directory):
                            topic_directory = topic_title.replace(' ', '_').replace('/', '_')
                            topic_path = os.path.join(write_directory, topic_directory)

                            if not os.path.exists(topic_path):
                                os.makedirs(topic_path)

                        write_path_topic = os.path.join(topic_path, topic_directory + '.html')
                        with open(write_path_topic, 'wb') as wf:
                            for comment in comments:
                                # pprint.pprint(comment)
                                # print(comment['id'], comment['content'])
                                # print('Writing --> ' + write_path_topic)

                                # Only pull down posts more recent than what is already on shotgun
                                postID = str(comment['id'])
                                if postID > latestPostID:
                                    postData = [str(comment['id']), comment['creator']['name'], comment['content'], comment['attachments'], comment['created_at']]
                                    usefulData.append(postData)
                                    wf.write('<h3>' + str(comment['id']) + '&nbsp' + comment['creator']['name'] + '&nbsp' +
                                             comment['created_at'] + '</h3><div>')
                                    if comment['content'] != None:
                                        wf.write(comment['content'].encode('ascii', 'replace'))
                                    wf.write('</br>')
                                    attachments = comment['attachments']
                                    if len(attachments) > 0:
                                        for attach in attachments:
                                            creator = attach['creator']['name'].replace(' ', '_')
                                            # print(attach['name'], creator)
                                            write_path_topic = os.path.join(topic_path, attach['name'])
                                            wf.write('<br><a href=\"' + attach['name'] + '\">' + attach[
                                                'name'] + '</a></br>')

                                            if not os.path.exists(write_path_topic):
                                                # print('Writing --> ' + write_path_topic)
                                                ff = requests.get(attach['url'], headers=headers_422, auth=auth_422)
                                                open(write_path_topic, 'wb').write(ff.content)
                                    wf.write('</div>')
                                else:
                                    continue
                else:
                    continue
    tmp = write_directory + topic_directory

    return usefulData, basecampName, tmp
