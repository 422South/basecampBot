import datetime
import os, re, sys
from flask import Flask, request
import requests
from re import search, IGNORECASE
import shotgun_api3 as sg3
import pprint
import shutil

SCRIPT_KEY = os.environ.get('SG_KEY')
SCRIPT_NAME = os.environ.get('SG_NAME')
SITE_URL = os.environ.get('SG_HOST') + '/api/v1'
sg = sg3.Shotgun(os.environ.get('SG_HOST'), SCRIPT_NAME, SCRIPT_KEY)

app = Flask(__name__)

write_directory = 'BasecampDownloads'
write_directory = write_directory + "/"


'''
    Function to return some <default> HTML if the user somehow accesses the local host website
'''


@app.route("/", methods=['GET', 'POST'])
def defaultLocalHost():
    return "<h1>This is a blank page..." + "</h1>"


'''
    Function to check authorisation for our shotgun site
'''


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
    # pprint.pprint(resp)
    return {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + resp.json()['access_token']
    }


'''
    Function to update all basecamp threads throughout the site
'''


@app.route("/basecamp/updateall", methods=['GET', 'POST'])
def updateAllThreads():
    if not os.path.exists(write_directory):
        os.mkdir(write_directory)

    notes = sg.find('Note', [['sg_basecamptopic', 'is_not', '']], ['sg_basecamptopic', 'sg_latestpostid', 'note_links'])
    for note in notes:
        latestID = note['sg_latestpostid']
        assetID = note['note_links'][0].get("id")
        basecamptopic = note['sg_basecamptopic']

        writeDirectory = createNote(latestID, basecamptopic, assetID)
        if os.path.exists(write_directory):
            if os.path.exists(writeDirectory):
                shutil.rmtree(writeDirectory, ignore_errors=True)

    return "<h1>Threads updated" + "</h1>"


'''
    Function to update a specific basecamp thread
'''


@app.route("/basecamp/confirm", methods=['GET', 'POST'])
def confirm():
    if not os.path.exists(write_directory):
        os.mkdir(write_directory)

    basecamptopic = request.args.get('topic')
    assetID = request.args.get('assetid')

    writeDirectory = createNote(0, basecamptopic, int(assetID))

    if os.path.exists(write_directory):
        if os.path.exists(writeDirectory):
            shutil.rmtree(writeDirectory, ignore_errors=True)

    return "<h1>Upload Successful!</h1>"


'''
    Actual creation of notes and replies on shotgun
'''


def createNote(latestPostID, baseCampTopic, assetId):

    asset = sg.find_one('Asset', [['id', 'is', assetId]], ['id', 'project'])

    baseCampTopic = re.sub(r'^.*?---', '', baseCampTopic)
    baseCampTopic = baseCampTopic.replace(' ', '_').replace('/', '_')

    basecampJSON, drainProject, writeDirectory = getBasecampFiles(latestPostID, baseCampTopic)

    theProjectID = asset['project'].get('id')
    # theProjectID = 289

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
                .replace('&gt;', '>') \
                .replace('&nbsp;', ' ')
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

    return writeDirectory


'''
    Function to process AMI and generate the web form to ask the user which thread to download
'''


@app.route("/basecamp/initiate", methods=['GET', 'POST'])
def process_ami():
    if not os.path.exists(write_directory):
        os.mkdir(write_directory)

    # pprint.pprint(request.form)
    auth_header = get_auth_header()

    assetTemp = request.form.get('selected_ids').split(',')
    asset_id = assetTemp[0]

    asset = sg.find_one('Asset', [['id', 'is', int(asset_id)]], ['id', 'code'])
    assetName = asset['code']

    '''
        Need to ask the user what the baseCampTopic is to continue
    '''
    found = False

    potentialNotes = sg.find('Note', [['note_links', 'name_contains', assetName]], ['sg_basecamptopic', 'sg_latestpostid'])
    for note in potentialNotes:
        if note['sg_basecamptopic'] is not None:
            found = True

    if found:

        if not os.path.exists(write_directory):
            os.mkdir(write_directory)

        writeDirectory = createNote(note['sg_latestpostid'], note['sg_basecamptopic'], int(asset_id))

        if os.path.exists(write_directory):
            if os.path.exists(writeDirectory):
                shutil.rmtree(writeDirectory, ignore_errors=True)

        return "<h1>A basecamp thread for this asset already exists, and has just been updated</h1>"

    else:
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
               '<label for="lname">' + str(assetName) + '<br>Please select a basecamp topic to attach to this asset</label><br><br>' \
               '<select name="topic" size="number_of_options">' \
               + htmlTmp + \
               '</select><br><br>' \
               '<input type="submit" value="Confirm"><br><br>' \
               '<label for="lname">This may take a while to download, this page will change when the operation is complete</label><br>' \
               '<input type="hidden" id="assetid" name="assetid" value="' + str(asset_id) + '" >' \
               '</form>'


'''
    Function to pull images / notes down from basecamp
'''


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
