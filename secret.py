# !/bin/env python
import json, os, boto3, base64
from botocore.exceptions import ClientError

def getSecretKeys():
    """Returns only the secret manager environment variables"""
    secretKeys = {}
    for key, value in os.environ.items():
        if key.startswith("SSM_"):
            secretKeys[key] = value
    if secretKeys:
        return secretKeys
    else:
        raise ValueError("Cannot find the Secrets Manager environment variable key, make sure there is atleast an env var with 'SSM_' prefix for the init-container")

def getSecretFileName():
    try:
        secretFile = os.environ["SECRET_FILE_PATH"]
    except KeyError:
        raise ValueError("Cannot find the secret file path, make sure there is an env var SECRET_FILE_PATH for the init-container")
    return secretFile

def get_secret(secret_name):
    try:
        region_name = os.environ["AWS_REGION"]
    except KeyError:
        raise ValueError("Cannot find the AWS Region, make sure there is an env var AWS_REGION for the init-container")
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name,
            VersionStage="AWSCURRENT"
        )
    except ClientError as e:
        raise e
    else:
        if 'SecretString' in get_secret_value_response and get_secret_value_response['SecretString']:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
            return decoded_binary_secret

def loadSecret(prefix, secret_name, secretFile):
    print("Saving", secret_name, "secrets to", secretFile.name)
    data=get_secret(secret_name)
    secret = json.loads(data)

    for key, value in secret.items():
        secretFile.write(key.upper() + "=" + "'" + str(value) + "'" + "\n")
    print("Done fetching secrets", secret_name)

print("Running init container script")
allSecrets = getSecretKeys()
secretFileName = getSecretFileName()
with open(secretFileName,"w") as secretFile:
    for key, secret_name in allSecrets.items():
        prefix = f'{key.split("_")[1]}_'
        loadSecret(prefix, secret_name, secretFile)
