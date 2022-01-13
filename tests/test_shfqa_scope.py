import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfqa
from zhinst.toolkit.driver.modules.shfqa_scope import SHFScope


@pytest.fixture()
def scope(session, shfqa):

    yield SHFScope(shfqa, session, ("scopes", "0"))


class TestSHFQAScope:
    def test_run(self, mock_connection, scope):
        # already enabled
        mock_connection.return_value.getInt.return_value = 1
        scope.run()
        mock_connection.return_value.set.assert_called_with(
            "/DEV1234/SCOPES/0/ENABLE", True
        )
        # never disabled
        mock_connection.return_value.getInt.return_value = 0
        with pytest.raises(TimeoutError) as e_info:
            scope.run(timeout=0.5)

    def test_stop(self, mock_connection, scope):
        # already disabled
        mock_connection.return_value.getInt.return_value = 0
        scope.stop()
        mock_connection.return_value.set.assert_called_with(
            "/DEV1234/SCOPES/0/ENABLE", False
        )
        # never disabled
        mock_connection.return_value.getInt.return_value = 1
        with pytest.raises(TimeoutError) as e_info:
            scope.stop(timeout=0.5)

    def test_wait_done(self, mock_connection, scope):
        # already disabled
        mock_connection.return_value.getInt.return_value = 0
        scope.wait_done()
        # never disabled
        mock_connection.return_value.getInt.return_value = 1
        with pytest.raises(TimeoutError) as e_info:
            scope.wait_done(timeout=0.5)

    def test_configure(self, mock_connection, scope):
        with patch(
            "zhinst.toolkit.driver.modules.shfqa_scope.deviceutils", autospec=True
        ) as deviceutils:
            scope.configure(
                scope.available_inputs[0], 10, scope.available_trigger_inputs[0]
            )
            deviceutils.configure_scope.assert_called_with(
                mock_connection.return_value,
                "DEV1234",
                scope.available_inputs[0],
                10,
                scope.available_trigger_inputs[0],
                1,
                1,
                0,
            )
            scope.configure(
                scope.available_inputs[0],
                10,
                scope.available_trigger_inputs[0],
                num_segments=0,
                num_averages=10,
                trigger_delay=33,
            )
            deviceutils.configure_scope.assert_called_with(
                mock_connection.return_value,
                "DEV1234",
                scope.available_inputs[0],
                10,
                scope.available_trigger_inputs[0],
                0,
                10,
                33,
            )

    def test_read(self, mock_connection, scope):
        with patch(
            "zhinst.toolkit.driver.modules.shfqa_scope.deviceutils", autospec=True
        ) as deviceutils:
            deviceutils.get_scope_data.return_value = (
                ["data1", "data2"],
                ["range1", "range2"],
                ["time1", "time2"],
            )
            recorded_data, recorded_data_range, scope_time = scope.read()
            deviceutils.get_scope_data.assert_called_with(
                mock_connection.return_value, "DEV1234", 10
            )
            assert recorded_data == ["data1", "data2"]
            assert recorded_data_range == ["range1", "range2"]
            assert scope_time == ["time1", "time2"]

            # timout argument is forwarded
            scope.read(timeout=1)
            deviceutils.get_scope_data.assert_called_with(
                mock_connection.return_value, "DEV1234", 1
            )

            # single channel
            recorded_data, recorded_data_range, scope_time = scope.read(channel=0)
            assert recorded_data == "data1"
            assert recorded_data_range == "range1"
            assert scope_time == "time1"
