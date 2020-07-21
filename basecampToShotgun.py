import datetime
import os, re, sys
from flask import Flask, request, abort
import requests
from re import search, IGNORECASE
import shotgun_api3 as sg3
import pprint
import shutil
import logging
import socket
import hashlib
import hmac
import time
import traceback

app = Flask(__name__)


def _setup_logger(level=logging.DEBUG, file='test.log', console_log=True):
    logger = logging.getLogger(os.path.basename(__file__))
    logger.setLevel(level)

    if file is not None:
        FORMAT = "[%(asctime)-15s %(levelname)s] %(message)s"
        fileHandler = logging.FileHandler(file)
        formatter = logging.Formatter(FORMAT)
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)
    if console_log:
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(formatter)
        logger.addHandler(console)
        logger.debug("Hostname: %s" % hostname)
    return logger


hostname = socket.gethostname()
if search('deadline', hostname, IGNORECASE):
    logger = _setup_logger(file='/var/log/httpd/basecamp_bot.log', console_log=False, level=logging.DEBUG)


else:
    logger = _setup_logger(file='basecamp_bot.log')

SCRIPT_KEY = os.environ.get('SG_KEY')
SCRIPT_NAME = os.environ.get('SG_NAME')
SITE_URL = os.environ.get('SG_HOST') + '/api/v1'

sg = sg3.Shotgun(os.environ.get('SG_HOST'), SCRIPT_NAME, SCRIPT_KEY)

curdir = os.path.dirname(__file__)
write_directory = os.path.join(curdir, 'BasecampDownloads/')

'''
    Function to authenticate that the application call has come from shotgun
'''


def checkAuthentication():
    key = 'MyBigSecret'
    sorted_params = []
    # Echo back information about what was posted in the form
    form = request.form
    if not 'signature' in form.keys():
        logger.debug("Request not signed")
        return False

    for field in form.keys():
        if field != "signature":
            sorted_params.append("%s=%s\r\n" % (field, form[field]))

    sorted_params.sort()
    string_to_verify = ''.join(sorted_params)
    signature = hmac.new(key, string_to_verify, hashlib.sha1).hexdigest()
    now = datetime.datetime.utcnow()
    request_time = datetime.datetime.strptime(form['timestamp'], "%Y-%m-%dT%H:%M:%SZ")
    delta = (now - request_time).total_seconds()

    if form.get('signature') == signature and delta < 10:
        return True
    else:
        return False


'''
    Function to return some <default> HTML if the user somehow accesses the local host website
'''


@app.route("/", methods=['GET', 'POST'])
def defaultLocalHost():
    logger.info("route : /")
    logger.debug(request.headers)
    if request.headers['host'] and search('^localhost', request.headers['host'], IGNORECASE):
        return ""
    authenticated = checkAuthentication()
    if not authenticated:
        abort(404)

    return ""


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
    pprint.pprint(resp)
    return {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + resp.json()['access_token']
    }


'''
    Function to update all basecamp threads throughout the site
'''


@app.route("/basecamp/checkProjects", methods=['GET', 'POST'])
def checkProjects():
    logger.info("route : /basecamp/checkProjects")

    localhost = request.headers['host'] and search('^localhost', request.headers['host'], IGNORECASE)
    if localhost:
        logger.debug("Localhost detected")
    else:
        authenticated = checkAuthentication()
        if not authenticated:
            abort(404)
            return ""

    htmlTmp = ""

    try:
        url = 'https://basecamp.com/2978927/api/v1/projects.json'
        headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
        auth_422 = ('craig@422south.com', 'Millenium2')
        r = requests.get(url, headers=headers_422, auth=auth_422)
        for basecampProject in r.json():
            if search('^drain', basecampProject['name'], IGNORECASE):
                topic_url = 'https://basecamp.com/2978927/api/v1/projects/' + str(
                    basecampProject['id']) + '/topics.json'
                t = requests.get(topic_url, headers=headers_422, auth=auth_422)
                topics = t.json()
                for topic in topics:
                    if topicAlreadyExists(topic['title']):
                        continue
                    temp = basecampProject['name'] + '---' + str(topic['title'])
                    htmlTmp = htmlTmp + '<option value="' + temp + '">' + temp + '</option>'

        return "<h2><p style='color: grey';>Unlinked Basecamp Threads: <br><br>" + htmlTmp + "</p></h2>"
    except:
        return "<h2><p style='color: grey';>An error occurred accessing basecamp</p></h2>"


@app.route("/basecamp/updateall", methods=['GET', 'POST'])
def updateAllThreads():
    logger.info("route : /basecamp/updateall")

    localhost = request.headers['host'] and search('^localhost', request.headers['host'], IGNORECASE)
    if localhost:
        logger.debug("Localhost detected")
    else:
        authenticated = checkAuthentication()
        if not authenticated:
            abort(404)
            return ""

    if not os.path.exists(write_directory):
        os.mkdir(write_directory)

    notes = sg.find('Note', [['sg_basecamptopic', 'is_not', '']], ['sg_basecamptopic', 'sg_latestpostid', 'note_links', 'sg_basecampidentifier'])
    for note in notes:
        latestID = note['sg_latestpostid']
        assetID = note['note_links'][0].get("id")
        basecamptopic = note['sg_basecamptopic']
        uniqueIdentifier = note['sg_basecampidentifier']

        logger.info("Upadating Asset %s with thread %s" % (note['note_links'][0]['name'], basecamptopic))

        if os.path.exists(write_directory + basecamptopic):
            # Skip this note for update as someone else is manually updating it
            continue

        try:
            writeDirectory = createNote(latestID, basecamptopic, assetID, uniqueIdentifier)
        except Exception as e:
            logger.debug("Update all thread failed to update thread: " + str(basecamptopic))

            group = sg.find_one("Group", [["code", "is", 'Data/Tech Management']], ["id"])
            asset = sg.find_one('Asset', [['id', 'is', assetID]], ['id', 'project'])
            theProjectID = asset['project'].get('id')

            track = traceback.format_exc()

            ticketData = {
                'project': {'type': 'Project', 'id': theProjectID},
                'title': 'Basecamp Bot Error with ' + basecamptopic,
                'description': str(track),
                'addressings_to': [{'type': 'Group', 'id': group['id']}],
            }
            sg.create('Ticket', ticketData)

            continue

        if os.path.exists(write_directory):
            if os.path.exists(writeDirectory):
                shutil.rmtree(writeDirectory, ignore_errors=True)
    logger.info("%d Threads updated" % len(notes))
    return "<h2><p style='color: grey';>Threads updated</p></h2>"


'''
    Function to update a specific basecamp thread
'''


@app.route("/basecamp/confirm", methods=['GET', 'POST'])
def confirm():
    logger.info("route : /basecamp/confirm")
    form = request.form
    if not form.has_key('key') and not form.has_key('assetid') and not form.has_key('timestamp'):
        abort(404)
        return ""

    key = form['key']
    assetID = form['assetid']
    timestamp = form['timestamp']
    now = datetime.datetime.utcnow()
    request_time = datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    delta = (now - request_time).total_seconds()
    if delta > 10:
        abort(404)
        return ""
    (quotient, remainder) = divmod(int(assetID) * 5476, 5)
    confirmKey = str(int(assetID) * 764389 + quotient + remainder)
    verifyKey = hmac.new('MyBigSecret', confirmKey, hashlib.sha1).hexdigest()

    if not key == verifyKey:
        abort(404)
        return ""

    if not os.path.exists(write_directory):
        os.mkdir(write_directory)

    basecamptopic = form['topic']
    logger.info(request)

    tmp = re.sub(r'^.*?---', '', basecamptopic).replace(' ', '_').replace('/', '_').replace(':', '_')

    if os.path.exists(write_directory + tmp):
        # Don't continue for update as someone else is manually updating it
        return "<h2><p style='color: grey';>Another user is currently attempting to update this thread!</p></h2>"

    try:
        writeDirectory = createNote(0, basecamptopic, int(assetID), 'New')
    except:
        logger.debug("Exception during create note")
        return "<h2><p style='color: grey';>I ran into an error creating a new note for this asset</p></h2>"

    if os.path.exists(write_directory):
        if os.path.exists(writeDirectory):
            shutil.rmtree(writeDirectory, ignore_errors=True)

    logger.info("Upload successful for %s" % request.form)

    return "<h2><p style='color: grey';>Upload Successful!</p></h2>"


'''
    Actual creation of notes and replies on shotgun
'''


def createNote(latestPostID, baseCampTopic, assetId, uniqueIdentifier):
    asset = sg.find_one('Asset', [['id', 'is', assetId]], ['id', 'project'])

    baseCampTopic = re.sub(r'^.*?---', '', baseCampTopic)
    baseCampTopic = baseCampTopic.replace(' ', '_').replace('/', '_').replace(':', '_')

    try:
        basecampJSON, drainProject, writeDirectory, topicID = getBasecampFiles(latestPostID, baseCampTopic, uniqueIdentifier)
    except:
        raise Exception('Error downloading files from basecamp')

    theProjectID = asset['project'].get('id')
    # theProjectID = 289

    # Find all users on the project
    userList = []
    project = sg.find("HumanUser", [["projects", "is", {'type': 'Project', "id": theProjectID}]], ["name"])
    for user in project:
        userList.append(user)

    # If the basecamp thread doesn't exist create it
    baseCampThread = sg.find_one('Note', [['subject', 'is', 'Basecamp Thread for ' + baseCampTopic],
                                          ['project', 'is', {'type': 'Project', "id": theProjectID}]], ['name'])
    if baseCampThread == None:
        note_data = {
            'project': {'type': 'Project', 'id': theProjectID},
            'subject': 'Basecamp Thread for ' + baseCampTopic,
            'content': 'Everything from basecamp for ' + baseCampTopic,
            'sg_basecamptopic': baseCampTopic,
            'sg_latestpostid': '0',
            'sg_basecampidentifier': str(topicID),
            'note_links': [{'type': 'Asset', 'id': asset['id']}],
            # 'addressings_to': userList,
            'suppress_email_notif': True,
        }
        sg.create('Note', note_data)

    # Build replies onto the new note or add to it if it already exists
    baseCampThread = sg.find_one('Note', [['subject', 'is', 'Basecamp Thread for ' + baseCampTopic],
                                          ['project', 'is', {'type': 'Project', "id": theProjectID}]], ['name'])
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
                .replace('&nbsp;', ' ') \
                .replace('<u>', '') \
                .replace('</u>', '') \
                .replace('<i>', '') \
                .replace('</i>', '')
        else:
            theContents = ""

        botUser = sg.find_one('ClientUser', [['name', 'is', 'Basecamp Bot']], ['name'])
        replyDateCreation = 'This note was created by ' + i[1] + ' on ' + i[4].replace('T', ' ').replace('.000Z',
                                                                                                         '') + '\n\n'
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
            if os.path.exists(imageLocation):
                img_id = sg.upload('Note', baseCampThread['id'], imageLocation)


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
    logger.info("route : /basecamp/initiate")

    authenticated = checkAuthentication()
    if not authenticated:
        abort(404)
        return ""

    if not os.path.exists(write_directory):
        os.mkdir(write_directory)

    # pprint.pprint(request.form)
    auth_header = get_auth_header()

    assetTemp = request.form.get('selected_ids').split(',')
    asset_id = assetTemp[0]

    asset = sg.find_one('Asset', [['id', 'is', int(asset_id)]], ['id', 'code', 'project'])
    assetName = asset['code']

    projectID = asset['project'].get('id')

    '''
        Need to ask the user what the baseCampTopic is to continue
    '''
    found = False

    potentialNotes = sg.find('Note', [['note_links', 'name_contains', assetName],
                                      ['project', 'is', {'type': 'Project', "id": projectID}]],
                             ['sg_basecamptopic', 'sg_latestpostid', 'subject', 'sg_basecampidentifier'])

    for note in potentialNotes:
        if note['sg_basecamptopic'] is not None:
            found = True
            break

    if found:

        try:
            if not os.path.exists(write_directory):
                os.mkdir(write_directory)

            if os.path.exists(write_directory + note['sg_basecamptopic']):
                # Don't continue for update as someone else is manually updating it
                return "<h2><p style='color: grey';>Another user is currently attempting to update this thread!</p></h2>"

            writeDirectory = createNote(note['sg_latestpostid'], note['sg_basecamptopic'], int(asset_id), note['sg_basecampidentifier'])

            if os.path.exists(write_directory):
                if os.path.exists(writeDirectory):
                    shutil.rmtree(writeDirectory, ignore_errors=True)

            return "<h2><p style='color: grey';>A basecamp thread for this asset already exists, and has just been updated</p></h2>"
        except:
            return "<h2><p style='color: grey';>I ran into an error attempting to update the note for asset " + str(
                assetName) + "</p></h2>"

    else:
        # print "Loading UI"
        htmlTmp = ""
        key = 'MyBigSecret'

        try:
            url = 'https://basecamp.com/2978927/api/v1/projects.json'
            headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
            auth_422 = ('craig@422south.com', 'Millenium2')
            r = requests.get(url, headers=headers_422, auth=auth_422)
            for basecampProject in r.json():
                if search('^drain', basecampProject['name'], IGNORECASE):
                    topic_url = 'https://basecamp.com/2978927/api/v1/projects/' + str(
                        basecampProject['id']) + '/topics.json'
                    t = requests.get(topic_url, headers=headers_422, auth=auth_422)
                    topics = t.json()
                    for topic in topics:
                        if topicAlreadyExists(topic['title']):
                            continue
                        temp = basecampProject['name'] + '---' + str(topic['title'])
                        htmlTmp = htmlTmp + '<option value="' + temp + '">' + temp + '</option>'
        except:
            return "<h2><p style='color: grey';>I ran into an error connecting to basecamp</p></h2>"
        (quotient, remainder) = divmod(int(asset_id) * 5476, 5)
        confirmKey = str(int(asset_id) * 764389 + quotient + remainder)
        signature = hmac.new(key, confirmKey, hashlib.sha1).hexdigest()

        js = "<script> \
                function submit_with_time(){ \
                document.getElementById('timestamp').value = new Date().toISOString(); \
                document.getElementById('info_text').innerHTML = \"Processing the Basecamp thread ... please be patient!\"; \
                document.getElementById(\"confirm_form\").submit(); \
                } \
                </script>"

        # return js + '<form name="confirm_form" action="/basecamp/confirm" method="post">' \

        return js + '<form id="confirm_form" action="/basecamp/confirm" method="post">' \
                    '<label for="lname"><p style="color: grey";>' + str(
                    assetName) + '<br>Please select a basecamp topic to attach to this asset</label><br><br>' \
                    '<select name="topic" size="number_of_options">' \
                    + htmlTmp + \
                    '</select><br><br>' \
                    '<input type="button" value="Confirm" onclick="submit_with_time()"><br><br>' \
                    '<label id="info_text" for="lname">This may take a while to download, this page will change when the operation is complete</label><br>' \
                    '<input type="hidden" id="assetid" name="assetid" value="' + str(asset_id) + '" >' \
                    '<input type="hidden" id="key" name="key" value="' + str(signature) + '" >' \
                    '<input type="hidden" id="timestamp" name="timestamp" value="" >' \
                    '</form>'


'''
    Function to pull images / notes down from basecamp
'''


def getBasecampFiles(latestPostID, baseCampTopic, uniqueIdentifier):
    url = 'https://basecamp.com/2978927/api/v1/projects.json'
    headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
    auth_422 = ('craig@422south.com', 'Millenium2')
    r = requests.get(url, headers=headers_422, auth=auth_422)
    basecampName = ""
    usefulData = []
    topicID = ""
    gotID = False
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
                tmp = topic_title.replace(' ', '_').replace('/', '_').replace(':', '_')
                topicID = topicName['id']
                if str(topicID) == uniqueIdentifier or (uniqueIdentifier == 'New' and tmp == baseCampTopic):
                    finalTopicID = topicID
                    basecampName = str(basecampProject['name']).replace(' ', '_').replace('/', '_').replace(':', '_')
                    message_url = topicName['topicable']['url']
                    m = requests.get(message_url, headers=headers_422, auth=auth_422)
                    messages = m.json()
                    # for mm in messages:
                    #     pprint.pprint(mm)
                    # pprint.pprint(messages['comments'])
                    comments = messages['comments']
                    topic_directory = ""
                    if len(comments) > 0:
                        topic_directory = topic_title.replace(' ', '_').replace('/', '_').replace(':', '_')
                        topic_path = os.path.join(write_directory, topic_directory)
                        if not os.path.exists(topic_path):
                            os.makedirs(topic_path)

                        write_path_topic = os.path.join(topic_path, topic_directory + '.html')
                        with open(write_path_topic, 'wb') as wf:
                            if latestPostID < str(1):
                                initialPostData = [0, messages['creator']['name'],
                                                   messages['content'],
                                                   messages['attachments'], messages['created_at']]
                                usefulData.append(initialPostData)

                                attachments = messages['attachments']
                                if len(attachments) > 0:
                                    for attach in attachments:
                                        write_path_topic = os.path.join(topic_path, attach['name'])

                                        if not os.path.exists(write_path_topic):
                                            # print('Writing --> ' + write_path_topic)
                                            ff = requests.get(attach['url'], headers=headers_422, auth=auth_422)
                                            if ff.headers['Content-Type'] == 'application/xml':
                                                logger.debug("Image file download failed %s" % ff.content)
                                                raise Exception('An error occurred downloading an image attachment')

                                            with open(write_path_topic, 'wb') as f:
                                                f.write(ff.content)
                            for comment in comments:

                                # Only pull down posts more recent than what is already on shotgun
                                postID = str(comment['id'])
                                if postID > latestPostID:

                                    postData = [str(comment['id']), comment['creator']['name'], comment['content'],
                                                comment['attachments'], comment['created_at']]
                                    usefulData.append(postData)
                                    wf.write(
                                        '<h3>' + str(comment['id']) + '&nbsp' + comment['creator']['name'] + '&nbsp' +
                                        comment['created_at'] + '</h3><div>')
                                    if comment['content'] is not None:
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
                                                if ff.headers['Content-Type'] == 'application/xml':
                                                    logger.debug("Image file download failed %s" % ff.content)
                                                    raise Exception('An error occurred downloading an image attachment')

                                                with open(write_path_topic, 'wb') as f:
                                                    f.write(ff.content)

                                    wf.write('</div>')
                                else:
                                    continue
                else:
                    continue
    tmp = write_directory + topic_directory

    return usefulData, basecampName, tmp, finalTopicID


def topicAlreadyExists(topic):
    topic = topic.replace(' ', '_').replace('/', '_').replace(':', '_')
    note = sg.find('Note', [['subject', 'is', 'Basecamp Thread for ' + topic]], ['name'])

    if len(note) > 0:
        return True

    return False
