import shotgun_api3 as sg3
import pprint

api_url = 'https://sg-422south.shotgunstudio.com'
api_key = 'qkbzprCczeqzjcrarxd5glgc^'
api_name = 'ch_api_02'

sg = sg3.Shotgun(api_url, api_name, api_key)

def test():
    # project = sg.find_one('Project', [['id', 'is', 289]])
    # print project

    # humanUser = sg.find_one('HumanUser', [['name', 'is', 'Alec Watkins']], ['projects'])
    # print humanUser

    userData = {
        'name': 'New User',
        'password_change_next_login': True,
    }
    sg.create('ClientUser', userData)


def createANote():

    baseCampThread = sg.find_one('Note', [['subject', 'is', 'Basecamp Thread for ' + '01_The_Arabia_REF_Build_-_Recon']], ['id'])

    reply_data = {
        'entity': baseCampThread,
        'content': 'An example reply',
        'user': {'type': 'HumanUser', 'id': 19, 'name': 'Alec Watkins'},
    }
    sg.create('Reply', reply_data)

    filePath = 'BasecampDownloads/01_The_Arabia_REF_Build_-_Recon/Emily_Eades_still_07.jpg'
    sg.upload('Note', baseCampThread['id'], filePath)


def func_print_symbols():
    pprint.pprint([symbol for symbol in sorted(dir(sg)) if not symbol.startswith('_')])


def func_list_projects(name='Test-Project01'):
    filters = [['name', 'is', name]]
    result = sg.find('Project', [], ['name', 'created_by'])

    return result


def func_test_asset_list():
    # filters = [['id', 'is', 1936]]
    # assets = sg.find_one('Asset', filters, ['name', 'code', 'description', 'tasks', 'sg_asset_type', 'project', 'notes'])

    project = sg.find("HumanUser", [["projects", "is", {'type': 'Project', "id": 289}]], ["name"])
    for users in project:
        print (users['name'])

    # print assets
    # assetName = assets['code']
    # print(assetName)
    # for note in assets['notes']:
    #     print note
    #     note_specific = sg.find_one('Note', [["id", "is", note['id']]], ['sg_basecamptopic', 'sg_latestpostid'])
        # print(note_specific)
        # print(note_specific['BasecampTopic'])
        # pprint.pprint(notes['name'])
        # for note in notes:
        #     pprint.pprint(note)

        # pprint.pprint(note['BasecampTopic'])
        # pprint.pprint(sg.find('Note', [['project', 'is', {'id': 289, 'name': 'Test-Project01', 'type': 'Project'}]],
        #                       ['name', 'code', 'description', 'tasks', 'sg_asset_type', 'project', 'notes', 'parents',
        #                        'image_source_entity']))
    # pprint.pprint(result)


def func_list_versions(version_id=7255):
    pprint.pprint(sg.find('Version', [['id', 'is', version_id]],
                          ['name', 'code', 'playlists', 'published_files', 'sg_path_to_movie', 'project', 'notes',
                           'sg_path_to_frames', 'created_by',
                           'image_source_entity']))


def func_describe_asset_fields(sg_type='Note'):
    pprint.pprint(sg.schema_field_read(sg_type))


# pprint.pprint(func_list_projects())
# func_test_asset_list()
# createANote()
# test()
# func_print_symbols()
# func_list_versions()
func_describe_asset_fields()
# pprint.pprint(sg.schema_field_read('LocalStorage'))
# pprint.pprint(sg.find('LocalStorage', [], ['name', 'id', 'code', 'path', 'windows_path']))
# pprint.pprint(sg.find('FilesystemLocation', [], ['name', 'id', 'code', 'path', 'windows_path']))