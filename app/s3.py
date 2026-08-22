
import json
from .aws import make_client, settings


s3_client = make_client("s3")


def build_key(user_id:int, fileName:str):
    return f"{settings.s3_prefix}/user_{user_id}/{fileName}"


def upload_file(user_id:int, fileName:str, content:bytes, content_type:str):
    key = build_key(user_id, fileName)

    s3_client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=content,
        ContentType=content_type
    )
    
    metadata = {
        "metadataAttributes": {
            "user_id": {
                "value": { "type":"NUMBER", "numberValue": user_id },
                "includeForEmbedding": False
            }        
        }
    }
    

    s3_client.put_object(
        Bucket=settings.s3_bucket,
        Key=f"{key}.metadata.json",
        Body=json.dumps(metadata).encode(),
        ContentType="application/json"
    )
    
    return key
    
