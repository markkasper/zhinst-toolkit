import pytest
import json
from unittest.mock import patch
from fixtures import mock_connection, data_dir, session, hf2_session
from zhinst.toolkit import DataServerSession
from zhinst.toolkit.nodetree import NodeTree


class TestDataServerSession:
    def test_setup(self, mock_connection, session):
        mock_connection.assert_called_once_with("localhost", 8004, 6)
        mock_connection.return_value.listNodesJSON.assert_called_once_with("/zi/*")
        assert repr(session) == "DataServerSession(localhost:8004)"
        assert not session.is_hf2_server

    def test_setup_hf2(self, mock_connection, hf2_session):
        mock_connection.assert_called_once_with("localhost", 8005, 1)
        mock_connection.return_value.listNodesJSON.assert_not_called()
        assert repr(hf2_session) == "HF2DataServerSession(localhost:8005)"
        assert hf2_session.is_hf2_server

    def test_existing_connection(self, data_dir, mock_connection):
        json_path = data_dir / "nodedoc_zi.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.listNodesJSON.return_value = nodes_json

        DataServerSession(connection=mock_connection)
        mock_connection.assert_not_called()
        mock_connection.listNodesJSON.assert_called_once_with("/zi/*")

    def test_existing_connection(self, data_dir, mock_connection):
        json_path = data_dir / "nodedoc_zi.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.listNodesJSON.return_value = nodes_json
        mock_connection.getString.return_value = "DataServer"

        DataServerSession(connection=mock_connection)
        mock_connection.assert_not_called()
        mock_connection.getString.assert_called_once_with("/zi/about/dataserver")
        mock_connection.listNodesJSON.assert_called_once_with("/zi/*")

        DataServerSession(connection=mock_connection, hf2=False)
        with pytest.raises(RuntimeError) as e_info:
            DataServerSession(connection=mock_connection, hf2=True)

    def test_existing_connection_hf2(self, mock_connection):
        mock_connection.getString.return_value = "HF2DataServer"

        DataServerSession(connection=mock_connection)
        mock_connection.assert_not_called()
        mock_connection.getString.assert_called_with("/zi/about/dataserver")
        mock_connection.listNodesJSON.assert_not_called()

        DataServerSession(connection=mock_connection, hf2=True)
        with pytest.raises(RuntimeError) as e_info:
            DataServerSession(connection=mock_connection, hf2=False)

    def test_wrong_port(self, mock_connection):
        def setup_side_effect(host, port, level):
            if level > 1:
                raise RuntimeError("Unsupported API level")
            return mock_connection.return_value

        mock_connection.side_effect = setup_side_effect
        # Test HF2 server
        mock_connection.return_value.getString.return_value = "HF2DataServer"
        DataServerSession(connection=("localhost", 8005))
        mock_connection.assert_called_with("localhost", 8005, 1)

        DataServerSession(connection=("localhost", 8005), hf2=True)
        with pytest.raises(RuntimeError) as e_info:
            DataServerSession(connection=("localhost", 8005), hf2=False)

    def test_connect_device(self, data_dir, mock_connection, session):

        connected_devices = ""

        def get_string_side_effect(arg):
            if arg == "/zi/devices":
                json_path = data_dir / "zi_devices.json"
                with json_path.open("r", encoding="UTF-8") as file:
                    nodes_json = file.read()
                return nodes_json
            if arg == "/zi/devices/connected":
                return connected_devices
            if arg == "/dev1234/features/devtype":
                return "Test"
            raise RuntimeError("ZIAPINotFoundException")

        mock_connection.return_value.getString.side_effect = get_string_side_effect

        def connect_device_side_effect(serial, _):
            nonlocal connected_devices
            json_path = data_dir / "zi_devices.json"
            with json_path.open("r", encoding="UTF-8") as file:
                devices = [key for key in json.loads(file.read()).keys()]
            if serial.upper() not in devices:
                raise RuntimeError("device not visible to server")
            if serial not in connected_devices:
                if not connected_devices:
                    connected_devices = serial
                else:
                    connected_devices = connected_devices + "," + serial

        mock_connection.return_value.connectDevice.side_effect = (
            connect_device_side_effect
        )

        json_path = data_dir / "nodedoc_dev1234.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.listNodesJSON.return_value = nodes_json

        # device not visible
        with pytest.raises(KeyError) as e_info:
            session.connect_device("dev1111")
        assert "dev1111" in e_info.value.args[0].lower()

        # device visible
        device = session.connect_device("dev1234")
        mock_connection.return_value.connectDevice.assert_called_with("dev1234", "1GbE")
        assert device.serial == "dev1234"
        assert device.device_type == "Test"
        assert device.__class__.__name__ == "BaseInstrument"

        # access connected device
        assert "dev1234" in session.devices
        assert device == session.devices["dev1234"]
        assert len(session.devices) == 1
        for dev in session.devices:
            assert dev == "dev1234"

        # delete existing device
        # connot be overwritten
        with pytest.raises(LookupError) as e_info:
            session.devices["dev1234"] = None

        with pytest.raises(RuntimeError) as e_info:
            session.devices.connect_hf2_device("dev1234")

        session.disconnect_device("dev1234")
        # Can be called as often as wanted
        session.disconnect_device("dev1234")

    def test_connect_device_h2(self, data_dir, mock_connection, hf2_session):
        def connect_device_side_effect(serial, _):
            if serial == "dev1111":
                raise RuntimeError("dev1111 not visible")

        mock_connection.return_value.connectDevice.side_effect = (
            connect_device_side_effect
        )

        def get_string_side_effect(arg):
            if arg == "/dev1234/features/devtype":
                return "Test"
            raise RuntimeError("ZIAPINotFoundException")

        mock_connection.return_value.getString.side_effect = get_string_side_effect

        json_path = data_dir / "nodedoc_dev1234.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.listNodesJSON.return_value = nodes_json

        # device not visible
        with pytest.raises(RuntimeError) as e_info:
            hf2_session.connect_device("dev1111")
        assert "dev1111" in e_info.value.args[0].lower()

        # device visible
        device = hf2_session.connect_device("dev1234")
        mock_connection.return_value.connectDevice.assert_called_with("dev1234", "USB")
        assert device.serial == "dev1234"
        assert device.device_type == "Test"
        assert device.__class__.__name__ == "BaseInstrument"

        # access connected device
        assert "dev1234" in hf2_session.devices
        assert device == hf2_session.devices["dev1234"]
        assert len(hf2_session.devices) == 1
        for dev in hf2_session.devices:
            assert dev == "dev1234"

        with pytest.raises(RuntimeError) as e_info:
            hf2_session.devices.connect_hf2_device("dev1234")

        # connect non HF2 device
        with patch(
            "zhinst.toolkit.data_server_session.ziPython.ziDiscovery", autospec=True
        ) as discovery:
            discovery.return_value.get.return_value = {"devicetype":"Test234"}
            with pytest.raises(RuntimeError) as e_info:
                hf2_session.connect_device("dev5678")
        assert "dev5678" in e_info.value.args[0].lower()
        assert "test234" in e_info.value.args[0].lower()

    def test_devices_visible(self, mock_connection, session):
        session.devices.visible()
        mock_connection.return_value.getString.assert_called_once_with(
            "/zi/devices/visible"
        )

        def get_string_side_effect(arg):
            if arg == "/zi/devices/visible":
                raise RuntimeError()

        mock_connection.return_value.getString.side_effect = get_string_side_effect
        with patch(
            "zhinst.toolkit.data_server_session.ziPython.ziDiscovery", autospec=True
        ) as discovery:
            session.devices.visible()
            discovery.return_value.findAll.assert_called_once()

    def test_sync(self, mock_connection, session):
        session.sync()
        mock_connection.return_value.sync.assert_called_once()

    def test_poll(self, mock_connection, session):
        # default call
        # empty result
        result = session.poll()
        mock_connection.return_value.poll.assert_called_with(
            0.1, 500, flags=0, flat=True
        )
        assert not result
        # with result
        # TODO

    def test_awg_module(self, data_dir, mock_connection, session):
        awg_module = session.awg_module
        assert awg_module == session.awg_module
        mock_connection.return_value.awgModule.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.awgModule.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(awg_module.nodetree, NodeTree)

    def test_daq_module(self, data_dir, mock_connection, session):
        daq_module = session.daq_module
        assert daq_module == session.daq_module
        mock_connection.return_value.dataAcquisitionModule.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.dataAcquisitionModule.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(daq_module.nodetree, NodeTree)

    def test_device_settings_module(self, data_dir, mock_connection, session):
        device_settings_module = session.device_settings_module
        assert device_settings_module == session.device_settings_module
        mock_connection.return_value.deviceSettings.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.deviceSettings.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(device_settings_module.nodetree, NodeTree)

    def test_impedance_module(self, data_dir, mock_connection, session):
        impedance_module = session.impedance_module
        assert impedance_module == session.impedance_module
        mock_connection.return_value.impedanceModule.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.impedanceModule.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(impedance_module.nodetree, NodeTree)

    def test_mds_module(self, data_dir, mock_connection, session):
        mds_module = session.mds_module
        assert mds_module == session.mds_module
        mock_connection.return_value.multiDeviceSyncModule.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.multiDeviceSyncModule.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(mds_module.nodetree, NodeTree)

    def test_pid_advisor_module(self, data_dir, mock_connection, session):
        pid_advisor_module = session.pid_advisor_module
        assert pid_advisor_module == session.pid_advisor_module
        mock_connection.return_value.pidAdvisor.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.pidAdvisor.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(pid_advisor_module.nodetree, NodeTree)

    def test_precompensation_advisor_module(self, data_dir, mock_connection, session):
        precompensation_advisor_module = session.precompensation_advisor_module
        assert precompensation_advisor_module == session.precompensation_advisor_module
        mock_connection.return_value.precompensationAdvisor.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.precompensationAdvisor.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(precompensation_advisor_module.nodetree, NodeTree)

    def test_qa_module(self, data_dir, mock_connection, session):
        qa_module = session.qa_module
        assert qa_module == session.qa_module
        mock_connection.return_value.quantumAnalyzerModule.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.quantumAnalyzerModule.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(qa_module.nodetree, NodeTree)

    def test_recorder_module(self, data_dir, mock_connection, session):
        recorder_module = session.recorder_module
        assert recorder_module == session.recorder_module
        mock_connection.return_value.record.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.record.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(recorder_module.nodetree, NodeTree)

    def test_scope_module(self, data_dir, mock_connection, session):
        scope_module = session.scope_module
        assert scope_module == session.scope_module
        mock_connection.return_value.scopeModule.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.scopeModule.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(scope_module.nodetree, NodeTree)

    def test_sweeper_module(self, data_dir, mock_connection, session):
        sweeper_module = session.sweeper_module
        assert sweeper_module == session.sweeper_module
        mock_connection.return_value.sweep.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.sweep.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(sweeper_module.nodetree, NodeTree)

    def test_zoom_fft_module(self, data_dir, mock_connection, session):
        zoom_fft_module = session.zoom_fft_module
        assert zoom_fft_module == session.zoom_fft_module
        mock_connection.return_value.zoomFFT.assert_called_once()
        json_path = data_dir / "nodedoc_daq_test.json"
        with json_path.open("r", encoding="UTF-8") as file:
            nodes_json = file.read()
        mock_connection.return_value.zoomFFT.return_value.listNodesJSON.return_value = (
            nodes_json
        )
        assert isinstance(zoom_fft_module.nodetree, NodeTree)
