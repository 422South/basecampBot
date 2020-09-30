import boto3
import ast
import os
import shotgun_api3 as sg3
import zipfile

# This is designed to sit on a Cron job that runs overnight to save bandwidth, potential hours 8pm - 6am

shotgunKeys = {}
with open('/var/www/basecamp_bot/shotgunApp/shotgunKeys.txt', 'r') as f:
    for line in f:
        name, value = line.strip().split("=")
        shotgunKeys[name] = value

api_url = shotgunKeys['api_url']
api_key = shotgunKeys['api_key']
api_name = shotgunKeys['api_name']
sg = sg3.Shotgun(api_url, api_name, api_key)

keys = {}
with open('/var/www/basecamp_bot/shotgunApp/s3keys.txt', 'r') as f:
    for line in f:
        name, value = line.strip().split("=")
        keys[name] = value

ACCESS_KEY = keys['ACCESS_KEY']
SECRET_KEY = keys['SECRET_KEY']
bucketName = '422-south-shotgun'
client = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)

potentialPubFiles = sg.find('PublishedFile', [['sg_cloudpublishstatus', 'is', 'Remote']],
                            ['sg_cloudpublishstatus', 'path_cache', 'id', 'sg_cloudpublishtextures',
                             'sg_cloudpublishfolderpath', 'path_cache_storage'])

for pubFile in potentialPubFiles:
    filePathMount = pubFile['path_cache_storage']['name']
    filePathBase = '/orion/Projects'

    orionLocation = os.path.join(filePathBase, pubFile['path_cache'])

    textures = pubFile['sg_cloudpublishtextures']
    amazonKey = pubFile['sg_cloudpublishfolderpath'] + '/' + os.path.basename(orionLocation)

    # Do the download of the maya scene
    try:
        os.makedirs(os.path.dirname(orionLocation))
    except:
        pass
    pathToSceneCloud = os.path.dirname(amazonKey) + '/' + os.path.splitext(os.path.basename(amazonKey))[0] + '.zip'
    pathToSceneOrion = os.path.join(os.path.dirname(orionLocation), os.path.splitext(os.path.basename(orionLocation))[0] + '.zip')
    clientResponse = client.download_file(bucketName, pathToSceneCloud, pathToSceneOrion)

    # Unzip the scene file
    fileToUnzip = os.path.join(os.path.dirname(orionLocation), os.path.splitext(os.path.basename(orionLocation))[0] + '.zip')
    with zipfile.ZipFile(fileToUnzip, 'r') as zip_ref:
        zip_ref.extractall(os.path.dirname(fileToUnzip))
    os.remove(fileToUnzip)

    # Download all the textures as well
    texturesDict = ast.literal_eval(textures)
    for textureInfo in texturesDict:
        linuxPath = os.path.join(filePathBase, textureInfo[0].replace('\\', '/'))
        # print linuxPath
        try:
            os.makedirs(os.path.dirname(linuxPath))
        except:
            pass
        pathToTextureCloud = os.path.dirname(pubFile['sg_cloudpublishfolderpath']) + '/' + os.path.splitext(os.path.basename(textureInfo[1]))[0] + '.zip'
        pathToTextureOrion = os.path.join(os.path.dirname(linuxPath), os.path.splitext(os.path.basename(linuxPath))[0] + '.zip')
        response = client.download_file(bucketName, pathToTextureCloud, pathToTextureOrion)

        textureToUnzip = os.path.join(os.path.dirname(linuxPath), os.path.splitext(os.path.basename(linuxPath))[0] + '.zip')
        with zipfile.ZipFile(textureToUnzip, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(textureToUnzip))
        os.remove(textureToUnzip)

    # Update this field to CloudOrion, so that this script doesn't attempt to download that file again
    updatedVerData = {
        'sg_cloudpublishstatus': 'RemoteSynced',
    }
    sg.update('PublishedFile', pubFile['id'], updatedVerData)