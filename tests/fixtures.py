import pytest
from unittest.mock import patch
from pathlib import Path
from zhinst.toolkit import DataServerSession
from zhinst.toolkit.driver.base import BaseInstrument
from zhinst.toolkit.driver.shfqa import SHFQA
from zhinst.toolkit.driver.shfsg import SHFSG


@pytest.fixture()
def data_dir(request):
    yield Path(request.fspath).parent / "data"

@pytest.fixture()
def mock_connection():
    with patch(
        "zhinst.toolkit.data_server_session.ziPython.ziDAQServer", autospec=True
    ) as connection:
        yield connection

@pytest.fixture()
def session(data_dir, mock_connection):
    json_path = data_dir / "nodedoc_zi.json"
    with json_path.open("r", encoding="UTF-8") as file:
        nodes_json = file.read()
    mock_connection.return_value.listNodesJSON.return_value = nodes_json
    yield DataServerSession()

@pytest.fixture()
def hf2_session(data_dir, mock_connection):
    mock_connection.return_value.getString.return_value = "HF2DataServer"
    yield DataServerSession(hf2=True)

@pytest.fixture()
def base_instrument(data_dir, mock_connection, session):

    json_path = data_dir / "nodedoc_dev1234.json"
    with json_path.open("r", encoding="UTF-8") as file:
        nodes_json = file.read()
    mock_connection.return_value.listNodesJSON.return_value = nodes_json

    yield BaseInstrument("DEV1234", "test_type", session)

@pytest.fixture()
def shfqa(data_dir, mock_connection, session):

    json_path = data_dir / "nodedoc_dev1234_shfqa.json"
    with json_path.open("r", encoding="UTF-8") as file:
        nodes_json = file.read()
    mock_connection.return_value.listNodesJSON.return_value = nodes_json

    yield SHFQA("DEV1234", "SHFQA4", session)

@pytest.fixture()
def shfsg(data_dir, mock_connection, session):

    json_path = data_dir / "nodedoc_dev1234_shfsg.json"
    with json_path.open("r", encoding="UTF-8") as file:
        nodes_json = file.read()
    mock_connection.return_value.listNodesJSON.return_value = nodes_json

    yield SHFSG("DEV1234", "SHFSG8", session)
