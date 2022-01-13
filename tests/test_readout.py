import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfqa
from zhinst.toolkit.driver.modules.readout import Readout


@pytest.fixture()
def readout(session, shfqa):

    yield Readout(shfqa, session, ("qachannels", "0", "readout"), 0)


class TestReadout:
    def test_configure_result_logger(self, mock_connection, readout):
        with patch(
            "zhinst.toolkit.driver.modules.readout.deviceutils", autospec=True
        ) as deviceutils:
            readout.configure_result_logger("test", 10)
            deviceutils.configure_result_logger_for_readout.assert_called_with(
                mock_connection.return_value, "DEV1234", 0, "test", 10, 1, 0
            )
            readout.configure_result_logger(
                "test2", 0, num_averages=2, averaging_mode=1
            )
            deviceutils.configure_result_logger_for_readout.assert_called_with(
                mock_connection.return_value,
                "DEV1234",
                0,
                "test2",
                0,
                2,
                1,
            )

    def test_run(self, mock_connection, readout):
        with patch(
            "zhinst.toolkit.driver.modules.readout.deviceutils", autospec=True
        ) as deviceutils:
            readout.run()
            deviceutils.enable_result_logger.assert_called_with(
                mock_connection.return_value,
                "DEV1234",
                0,
                "readout",
            )

    def test_stop(self, mock_connection, readout):
        # already disabled
        mock_connection.return_value.getInt.return_value = 0
        readout.stop()
        mock_connection.return_value.set.assert_called_with(
            "/DEV1234/QACHANNELS/0/READOUT/RESULT/ENABLE", False
        )
        # never disabled
        mock_connection.return_value.getInt.return_value = 1
        with pytest.raises(TimeoutError) as e_info:
            readout.stop(timeout=0.5)

    def test_wait_done(self, mock_connection, readout):
        # already disabled
        mock_connection.return_value.getInt.return_value = 0
        readout.wait_done()
        # never disabled
        mock_connection.return_value.getInt.return_value = 1
        with pytest.raises(TimeoutError) as e_info:
            readout.wait_done(timeout=0.5)

    def test_read(self, mock_connection, readout):
        with patch(
            "zhinst.toolkit.driver.modules.readout.deviceutils", autospec=True
        ) as deviceutils:
            readout.read()
            deviceutils.get_result_logger_data.assert_called_with(
                mock_connection.return_value, "DEV1234", 0, "readout", 10
            )
            readout.read(timeout=1)
            deviceutils.get_result_logger_data.assert_called_with(
                mock_connection.return_value, "DEV1234", 0, "readout", 1
            )

    def test_set_integration_weight(self, mock_connection, readout):
        mock_connection.return_value.getInt.return_value = 100
        readout.set_integration_weight(0, np.zeros(100))
        mock_connection.return_value.setVector.assert_called()
        mock_connection.return_value.setInt.assert_not_called()

        mock_connection.reset_mock()
        mock_connection.return_value.getInt.return_value = 1000
        readout.set_integration_weight(0, np.zeros(100))
        mock_connection.return_value.setVector.assert_called()
        mock_connection.return_value.set.assert_called_once_with('/DEV1234/QACHANNELS/0/READOUT/INTEGRATION/LENGTH', 100)
