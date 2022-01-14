import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfsg
from zhinst.toolkit import SHFQAChannelMode
from zhinst.toolkit.driver.shfsg import SGChannel, AWGModule, Node


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
        # Wildcards nodes will be converted into normal Nodes
        assert not isinstance(shfsg.sgchannels["*"], SGChannel)
        assert isinstance(shfsg.sgchannels["*"], Node)

    def test_sg_awg(self, shfsg):
        assert isinstance(shfsg.sgchannels[0].awg, AWGModule)
        assert shfsg.sgchannels[0].awg.root == shfsg.root
        assert shfsg.sgchannels[0].awg.raw_tree == shfsg.raw_tree + (
            "sgchannels",
            "0",
            "awg",
        )

    def test_sg_awg_modulation_freq(self, mock_connection, shfsg):

        mock_connection.return_value.getInt.return_value = 0
        shfsg.sgchannels[0].awg_modulation_freq()
        mock_connection.return_value.getInt.assert_called_with("/DEV1234/SGCHANNELS/0/SINES/0/OSCSELECT")
        mock_connection.return_value.getDouble.assert_called_with("/DEV1234/SGCHANNELS/0/OSCS/0/FREQ")
        mock_connection.return_value.getInt.return_value = 1
        shfsg.sgchannels[0].awg_modulation_freq()
        mock_connection.return_value.getInt.assert_called_with("/DEV1234/SGCHANNELS/0/SINES/0/OSCSELECT")
        mock_connection.return_value.getDouble.assert_called_with("/DEV1234/SGCHANNELS/0/OSCS/1/FREQ")

