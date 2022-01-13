import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfqa
from zhinst.toolkit import SHFQAChannelMode
from zhinst.toolkit.driver.shfqa import (
    QAChannel,
    SHFScope,
    Generator,
    Readout,
    SHFSweeper,
)


class TestSHFQA:
    def test_repr(self, shfqa):
        assert repr(shfqa) == "SHFQA(SHFQA4,DEV1234)"

    def test_factory_reset(self, shfqa):
        # factory reset not yet implemented
        with pytest.warns(RuntimeWarning) as record:
            shfqa.factory_reset()

    def test_start_continuous_sw_trigger(self, mock_connection, shfqa):
        with patch(
            "zhinst.toolkit.driver.shfqa.deviceutils", autospec=True
        ) as deviceutils:
            shfqa.start_continuous_sw_trigger(10, 20.0)
            deviceutils.start_continuous_sw_trigger.assert_called_once_with(
                mock_connection.return_value, "DEV1234", 10, 20.0
            )
    def test_max_qubits_per_channel(self, shfqa):
        with patch(
            "zhinst.toolkit.driver.shfqa.deviceutils", autospec=True
        ) as deviceutils:
            shfqa.max_qubits_per_channel
            # cached property -> second call should not call device_utils
            shfqa.max_qubits_per_channel
            deviceutils.max_qubits_per_channel.assert_called_once()

    def test_qachannels(self, shfqa):
        assert shfqa.num_qachannels == 4
        assert len(shfqa.qachannels) == 4
        assert isinstance(shfqa.qachannels[0], QAChannel)

    def test_scopes(self, shfqa):
        assert shfqa.num_scopes == 1
        assert len(shfqa.scopes) == 1
        assert isinstance(shfqa.scopes[0], SHFScope)

    def test_qa_configure_channel(self, mock_connection, shfqa):
        with patch(
            "zhinst.toolkit.driver.shfqa.deviceutils", autospec=True
        ) as deviceutils:
            shfqa.qachannels[0].configure_channel(
                10, 20, 30.0, SHFQAChannelMode.READOUT
            )
            deviceutils.configure_channel.assert_called_once_with(
                mock_connection.return_value, "DEV1234", 0, 10, 20, 30.0, "readout"
            )

    def test_qa_num_intergrations(self, shfqa):
        assert shfqa.qachannels[0].num_integrations == 16

    def test_qa_generator(self, shfqa):
        assert isinstance(shfqa.qachannels[0].generator, Generator)
        assert shfqa.qachannels[0].generator.root == shfqa.root
        assert shfqa.qachannels[0].generator.raw_tree == shfqa.raw_tree +(
            "qachannels",
            "0",
            "generator",
        )

    def test_qa_readout(self, shfqa):
        assert isinstance(shfqa.qachannels[0].readout, Readout)
        assert shfqa.qachannels[0].readout.root == shfqa.root
        assert shfqa.qachannels[0].readout.raw_tree == shfqa.raw_tree +(
            "qachannels",
            "0",
            "readout",
        )

    def test_qa_sweeper(self, shfqa):
        assert isinstance(shfqa.qachannels[0].sweeper, SHFSweeper)
