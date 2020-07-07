import datetime
import os, re, sys
from flask import Flask, request
import requests
from re import search, IGNORECASE
import shotgun_api3 as sg3

import Tkinter as tk
from Tkinter import *

SCRIPT_KEY = os.environ.get('SG_KEY')
SCRIPT_NAME = os.environ.get('SG_NAME')
SITE_URL = os.environ.get('SG_HOST') + '/api/v1'
sg = sg3.Shotgun(os.environ.get('SG_HOST'), SCRIPT_NAME, SCRIPT_KEY)

app = Flask(__name__)

write_directory = 'BasecampDownloads/'


# @app.route("/hello", methods=['GET'])
def hello():
    return "<h1>Hello World " + datetime.datetime.now().strftime('%H:%M:%S') + "</h1>"


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

    return {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + resp.json()['access_token']
    }


def carryOn(latestPostID, baseCampTopic, assetId):

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

        isClient = False

        humanUser = sg.find_one('HumanUser', [['name', 'is', i[1]]], ['id'])
        if humanUser == None:

            isClient = True
            clientUser = sg.find_one('ClientUser', [['name', 'is', i[1]]], ['id'])
            if clientUser == None:
                userData = {
                    'name': i[1],
                    'password_change_next_login': True,
                }
                sg.create('ClientUser', userData)

        replyDateCreation = 'This note was created on ' + i[4].replace('T', ' ').replace('.000Z', '') + '\n\n'

        if not isClient:
            reply_data = {
                'entity': baseCampThread,
                'content': replyDateCreation + '' + theContents,
                'user': humanUser
            }
            sg.create('Reply', reply_data)
        else:
            reply_data = {
                'entity': baseCampThread,
                'content': replyDateCreation + '' + theContents,
                'user': clientUser
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


@app.route("/", methods=['GET', 'POST'])
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
                    carryOn(latestPostID, baseCampTopic, asset_id)

        if not found:
            '''
                Need to ask the user what the baseCampTopic is to continue
            '''

            print "Loading UI"
            window = tk.Tk()

            #  Window width, height and calculating the window to appear in the center of the screen
            width = 1600
            height = 650
            posRight = int(window.winfo_screenwidth() / 2 - width / 2)
            posDown = int(window.winfo_screenheight() / 2 - height / 2)
            window.geometry("+%d+%d" % (posRight, posDown))
            window.title("Select BaseCamp Topic")  # Window title
            window.resizable(0, 0)  # Make window non resizable by user
            topFrame = Frame(window, width=115, height=10, pady=20, padx=20)
            topFrame.pack(side=TOP)
            listBox = Listbox(topFrame, height=20, width=75, fg='black', exportselection=False)

            def onSelect(event):
                confirmBtn.config(state=ACTIVE)

            listBox.bind('<<ListboxSelect>>', onSelect)
            listBox.grid(row=2, column=0)

            scrollbarVertical = Scrollbar(topFrame, orient=VERTICAL)
            scrollbarHorizontal = Scrollbar(topFrame, orient=HORIZONTAL)
            scrollbarVertical.config(command=listBox.yview)
            scrollbarHorizontal.config(command=listBox.xview)
            scrollbarVertical.grid(row=2, column=1, sticky=N + S + W)
            scrollbarHorizontal.grid(row=3, column=0, sticky=E + W + S)
            listBox.config(yscrollcommand=scrollbarVertical.set, xscrollcommand=scrollbarHorizontal.set)

            confirmBtn = Button(topFrame, width=30, height=2, text="Confirm", command=lambda: [carryOn(0, listBox.get(listBox.curselection(), last=None), asset_id), window.destroy()], state=DISABLED)
            confirmBtn.grid(row=4, column=0, padx=1, pady=3)
            cancelBtn = Button(topFrame, width=30, height=2, text='Cancel', command=lambda: doClose())
            cancelBtn.grid(row=5, column=0, padx=1, pady=3)

            url = 'https://basecamp.com/2978927/api/v1/projects.json'
            headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
            auth_422 = ('craig@422south.com', 'Millenium2')
            r = requests.get(url, headers=headers_422, auth=auth_422)
            for oo in r.json():
                if search('^drain', oo['name'], IGNORECASE):
                    topic_url = 'https://basecamp.com/2978927/api/v1/projects/' + str(oo['id']) + '/topics.json'
                    t = requests.get(topic_url, headers=headers_422, auth=auth_422)
                    topics = t.json()
                    for tt in topics:
                        listBox.insert(END, oo['name'] + '---' + str(tt['title']))

            window.protocol("WM_DELETE_WINDOW", lambda: doClose())
            window.attributes('-topmost', 'true')

            def doClose():
                window.destroy()

            window.mainloop()

            return "<h1>Hello World " + datetime.datetime.now().strftime('%H:%M:%S') + "</h1>"


def getBasecampFiles(latestPostID, baseCampTopic):
    url = 'https://basecamp.com/2978927/api/v1/projects.json'
    headers_422 = {'Content-Type': 'application/json', 'User-Agent': '422App (craig@422south.com)'}
    auth_422 = ('craig@422south.com', 'Millenium2')
    r = requests.get(url, headers=headers_422, auth=auth_422)
    drainProject = ""
    usefulData = []
    # pprint.pprint(r.json(), indent= 5)
    for oo in r.json():
        if search('^drain', oo['name'], IGNORECASE):
            # pprint.pprint(oo['name'])
            topic_url = 'https://basecamp.com/2978927/api/v1/projects/' + str(oo['id']) + '/topics.json'
            # print(topic_url)
            t = requests.get(topic_url, headers=headers_422, auth=auth_422)
            topics = t.json()
            # pprint.pprint(topics)
            for tt in topics:
                # pprint.pprint(tt)
                # print(tt['title'], tt['topicable']['url'])
                topic_title = tt['title']

                # Only pull down the topic that is relevant
                tmp = topic_title.replace(' ', '_').replace('/', '_')
                if tmp == baseCampTopic:
                    drainProject = str(oo['name']).replace(' ', '_').replace('/', '_')
                    message_url = tt['topicable']['url']
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

    return usefulData, drainProject, tmp
