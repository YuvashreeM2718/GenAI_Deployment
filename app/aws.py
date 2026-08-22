
import boto3
from .config import get_settings

settings = get_settings()

def make_client(service:str):
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        return boto3.client(
            service,
            region_name = settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
        
    return boto3.client( service, region_name = settings.aws_region )
        
    