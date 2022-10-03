# Import external modules
from enum import Enum
import random
from app.server.modules.endpoints.file_creation_event import FileCreationEvent
from faker import Faker
from faker.providers import internet, lorem


# Import internal modules
from flask import current_app
from app.server.models import *
from app.server.modules.endpoints.file_creation_event import FileCreationEvent
from app.server.modules.logging.uploadLogs import LogUploader
from app.server.modules.clock.Clock import Clock
from app.server.utils import *
from app.server.modules.constants.legit_files import *

# instantiate faker
fake = Faker()
fake.add_provider(internet)
fake.add_provider(lorem)

def gen_system_files_on_host(count_of_events:int=10) -> None:
    """
    Generates FileCreationEvents for system files generated on a host
    {
            "creation_time": 2022-10-03 12:30:00
            "hostname": GXDR-4310,
            "sha256": 269eb0728413654856f4b2ee1fa7838cd69672ebc11baed4caa63f58c2df5823,
            "path": C:/Windows/System32/xcopy.exe,
            "filename": xcopy.exe,
            "size": 4510
    }
    """
    hash_path_pairs = random.choices(list(LEGIT_WINDOWS_FILES.items()), k=count_of_events)
    for hash, path in hash_path_pairs:
        file_creation_event = FileCreationEvent(
            hostname=get_random_employee().hostname, #Pick a random employee to generate system files
            creation_time=get_time(),
            filename=path.split("/")[-1], # Get the filename from the path 
            path="C:/"+path, # Add a drive letter
            sha256=hash
        )
        upload_endpoint_event_to_azure(file_creation_event)


def upload_endpoint_event_to_azure(event: FileCreationEvent, table_name: str = "FileCreationEvents") -> None:

    """
    A function to upload a FileCreationEvent to ADX
    References global LOG_UPLOADER to queue log rows for uploading
    """

    from app.server.game_functions import LOG_UPLOADER
    LOG_UPLOADER.send_request(
        data=[event.stringify()],
        table_name=table_name)