import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfsg
from zhinst.toolkit.driver.modules.command_table import CommandTable


@pytest.fixture()
def command_table(shfsg):
    yield CommandTable(
        shfsg.root,
        ("sgchannels", "0", "awg", "commandtable"),
        ct_schema_url="https://docs.zhinst.com/shfsg/commandtable/v1_0/schema",
    )


class TestCommandTable:
    def test_attributes(self, command_table):
        assert command_table.ct_schema_version == "1.0"
        assert command_table.raw_tree == ("sgchannels", "0", "awg", "commandtable")

    def test_load(self, mock_connection, command_table):
        command_table.load([])
        mock_connection.return_value.setVector.assert_called_with(
            "/DEV1234/SGCHANNELS/0/AWG/COMMANDTABLE/DATA",
            (
                '{"$schema": "https://docs.zhinst.com/shfsg/commandtable/v1_0/schema", '
                '"table": [], "header": [{"version": "1.0"}]}'
            ),
        )
        command_table.load(["test"])
        mock_connection.return_value.setVector.assert_called_with(
            "/DEV1234/SGCHANNELS/0/AWG/COMMANDTABLE/DATA",
            (
                '{"$schema": "https://docs.zhinst.com/shfsg/commandtable/v1_0/schema", '
                '"table": ["test"], "header": [{"version": "1.0"}]}'
            ),
        )
        command_table.load(
            {
                "$schema": "",
                "table": ["hello"],
                "header": [{"version": "2.0"}],
            }
        )
        mock_connection.return_value.setVector.assert_called_with(
            "/DEV1234/SGCHANNELS/0/AWG/COMMANDTABLE/DATA",
            '{"$schema": "", "table": ["hello"], "header": [{"version": "2.0"}]}',
        )

        command_table.load(
            '{"$schema": "", "table": ["ohhhno"], "header": [{"version": "2.0"}]}'
        )
        mock_connection.return_value.setVector.assert_called_with(
            "/DEV1234/SGCHANNELS/0/AWG/COMMANDTABLE/DATA",
            '{"$schema": "", "table": ["ohhhno"], "header": [{"version": "2.0"}]}',
        )

        with pytest.raises(RuntimeError) as e_info:
            command_table.load(1)

    def test_invalid_schema(self, mock_connection, shfsg, caplog):
        command_table = CommandTable(
            shfsg.root,
            ("sgchannels", "0", "awg", "commandtable"),
            ct_schema_url="https://docs.zhinst.com/shfsg/commandtable/v1_0/invalid",
        )
        assert len(caplog.records) == 1
        with pytest.raises(RuntimeError) as e_info:
            command_table.load([], validate=True)
        mock_connection.return_value.setVector.assert_not_called()
