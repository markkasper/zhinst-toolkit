import pytest
from fixtures import mock_connection, data_dir, session, hf2_session, base_instrument
from zhinst.toolkit.driver.base import BaseInstrument

class TestBaseInstrument:

    def test_basic_setup(self, mock_connection, base_instrument):
        mock_connection.return_value.listNodesJSON.assert_called_with(
            f"/{base_instrument.serial}/*"
        )

        assert base_instrument.device_type == "test_type"
        assert base_instrument.serial == "DEV1234"
        assert repr(base_instrument) == "BaseInstrument(test_type,DEV1234)"

    def test_hf2_setup(self, data_dir, mock_connection, hf2_session):
        list_nodes_path = data_dir / "list_nodes_hf2_dev.txt"
        with list_nodes_path.open("r", encoding="UTF-8") as file:
            nodes_dev = file.read().split("\n")[:-1]
        mock_connection.return_value.listNodes.return_value = nodes_dev

        instrument = BaseInstrument("DEV1234", "HF2LI", hf2_session)

        assert instrument.device_type == "HF2LI"
        assert instrument.serial == "DEV1234"
        assert repr(instrument) == "BaseInstrument(HF2LI,DEV1234)"

    def test_factory_reset(self, base_instrument, mock_connection):
        base_instrument.factory_reset()
        dev_id = base_instrument.serial.upper()
        mock_connection.return_value.syncSetInt.assert_called_once_with(
            f"/{dev_id}/SYSTEM/PRESET/LOAD", 1
        )

    def test_get_streamingnodes(self, base_instrument):
        nodes = base_instrument.get_streamingnodes()

        assert "auxin0" in nodes
        assert nodes["auxin0"].raw_tree == ("auxins", "0", "sample")
        assert "scope0" in nodes
        assert nodes["scope0"].raw_tree == ("scopes", "0", "stream", "sample")
        assert "demod0" in nodes
        assert nodes["demod0"].raw_tree == ("demods", "0", "sample")
        assert "demod1" in nodes
        assert nodes["demod1"].raw_tree == ("demods", "1", "sample")
        assert "pid0_value" in nodes
        assert nodes["pid0_value"].raw_tree == ("pids", "0", "stream", "value")

    def test_set_transaction(self, base_instrument):
        assert base_instrument.set_transaction == base_instrument.root.set_transaction


    def test_node_access(self, base_instrument):

        assert (
            base_instrument.demods[0].rate == base_instrument.root.demods[0].rate
        )
        assert (
            base_instrument["demods"][0].rate
            == base_instrument.root.demods[0].rate
        )

        assert "demods" in base_instrument
        for element in dir(base_instrument.root):
            assert element in dir(base_instrument)

        assert base_instrument._test == None

    def test_iter_nodetree(self, base_instrument):
        for res_base, res_nodetree in zip(base_instrument, base_instrument.root):
            assert res_base == res_nodetree

    def test_load_preloaded_json(self, base_instrument, mock_connection, data_dir):

        assert base_instrument._load_preloaded_json(data_dir) == None

        mock_connection.return_value.listNodes.side_effect = [["/dev1234/stats/0/temp"]]
        return_value = base_instrument._load_preloaded_json(data_dir / "preloadable_nodetree.json")
        assert len(return_value) == 1
        assert "/dev1234/stats/0/temp" in return_value

        mock_connection.return_value.listNodes.side_effect = [["/dev1234/stats/0/test"]]
        return_value = base_instrument._load_preloaded_json(data_dir / "preloadable_nodetree.json")
        assert len(return_value) == 0
