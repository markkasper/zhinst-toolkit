import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfsg
from zhinst.toolkit import SHFQAChannelMode
from zhinst.toolkit.driver.shfsg import SGChannel, AWGModule


class TestSHFSG:
    def test_repr(self, shfsg):
        assert repr(shfsg) == "SHFSG(SHFSG8,DEV1234)"

    def test_factory_reset(self, shfsg):
        # factory reset not yet implemented
        with pytest.warns(RuntimeWarning) as record:
            shfsg.factory_reset()

    def test_enable_qccs_mode(self, mock_connection, shfsg):
        shfsg.enable_qccs_mode()
        mock_connection.return_value.set.assert_called_once_with(
            "/DEV1234/SYSTEM/CLOCKS/REFERENCECLOCK/IN/SOURCE", 2
        )

    def test_enable_manual_mode(self, mock_connection, shfsg):
        shfsg.enable_manual_mode()
        mock_connection.return_value.set.assert_called_once_with(
            "/DEV1234/SYSTEM/CLOCKS/REFERENCECLOCK/IN/SOURCE", 0
        )

    def test_sgchannels(self, shfsg):
        assert shfsg.num_sgchannels == 16
        assert len(shfsg.sgchannels) == 16
        assert isinstance(shfsg.sgchannels[0], SGChannel)

    def test_sg_awg(self, shfsg):
        assert isinstance(shfsg.sgchannels[0].awg, AWGModule)
        assert shfsg.sgchannels[0].awg.root == shfsg.root
        assert shfsg.sgchannels[0].awg.raw_tree == shfsg.raw_tree + (
            "sgchannels",
            "0",
            "awg",
        )
