import pytest
from itertools import cycle
from unittest.mock import patch
from collections import OrderedDict
import json
import numpy as np
from fixtures import mock_connection, data_dir, session, shfsg
import zhinst.utils as zi_utils
from zhinst.toolkit.driver.modules.awg import AWGModule, CommandTable, Waveforms


@pytest.fixture()
def awg_module(shfsg, data_dir, mock_connection, session):
    json_path = data_dir / "nodedoc_awg_test.json"
    with json_path.open("r", encoding="UTF-8") as file:
        nodes_json = file.read()
    mock_connection.return_value.awgModule.return_value.listNodesJSON.return_value = (
        nodes_json
    )
    yield AWGModule(shfsg, session, ("sgchannels", "0", "awg"), 0, "test")


class TestAWG:
    def test_wait_done(self, mock_connection, awg_module):
        single = 0
        enable = iter([])

        def get_int_side_effect(node):
            if node.upper() == "/DEV1234/SGCHANNELS/0/AWG/SINGLE":
                return single
            if node.upper() == "/DEV1234/SGCHANNELS/0/AWG/ENABLE":
                return next(enable)

        mock_connection.return_value.getInt.side_effect = get_int_side_effect

        # if not single mode this function throws a RuntimeError
        with pytest.raises(RuntimeError) as e_info:
            awg_module.wait_done()

        # already finished
        single = 1
        enable = iter([0] * 2)
        awg_module.wait_done()
        # finishes in time
        single = 1
        enable = iter([1] * 3 + [0] * 2)
        awg_module.wait_done()
        # don't finish
        single = 1
        enable = cycle([1])
        with pytest.raises(TimeoutError) as e_info:
            awg_module.wait_done(timeout=0.1)

    def test_load_sequencer_program(self, mock_connection, awg_module, caplog):
        compiler_status = 0
        upload_process = iter([0, 0.2, 1, 1])
        ready = 1
        elf_status = 0

        def get_side_effect(node):
            if node == "/compiler/status":
                return compiler_status
            if node == "/progress":
                return next(upload_process)
            if node == "/elf/status":
                return elf_status
            if node == "/DEV1234/SGCHANNELS/0/AWG/READY":
                return ready
            return RuntimeError("Undefined Node")

        awg_mock = mock_connection.return_value.awgModule.return_value
        awg_mock.getDouble.side_effect = get_side_effect
        awg_mock.getInt.side_effect = get_side_effect
        mock_connection.return_value.getInt.side_effect = get_side_effect

        # everything ok
        awg_module.load_sequencer_program("Hello")
        awg_mock.set.assert_any_call("/device", "DEV1234")
        awg_mock.set.assert_any_call("/index", 0)
        awg_mock.set.assert_called_with("/compiler/sourcestring", "Hello")
        awg_mock.execute.assert_called()

        # Compiler timeout
        compiler_status = -1
        with pytest.raises(TimeoutError) as e_info:
            awg_module.load_sequencer_program("Hello", timeout=0.5)

        # Compiler error
        compiler_status = 1
        with pytest.raises(RuntimeError) as e_info:
            awg_module.load_sequencer_program("Hello")

        # Compiler warning
        compiler_status = 2
        awg_module.load_sequencer_program("Hello")
        assert "Warning during sequencer compilation" in caplog.messages[-1]
        compiler_status = 0

        # Upload timeout
        elf_status = 2
        ready = 0
        upload_process = cycle([0])
        with pytest.raises(TimeoutError) as e_info:
            awg_module.load_sequencer_program("Hello", timeout=0.5)

        # Upload error
        upload_process = cycle([1])
        with pytest.raises(RuntimeError) as e_info:
            awg_module.load_sequencer_program("Hello", timeout=0.5)

    def test_command_table(self, awg_module):
        assert isinstance(awg_module.commandtable, CommandTable)
        assert awg_module.commandtable.raw_tree == awg_module.raw_tree + (
            "commandtable",
        )

    def test_waveforms(self, caplog):
        waveform = Waveforms()
        wave1 = 1.0 * np.ones(1008)
        wave1_short = 1.0 * np.ones(500)
        wave2 = -1.0 * np.ones(1008)
        wave2_short = 2.0 * np.ones(500)
        wave3 = -0.5 * np.ones(1008)
        marker = 0.0 * np.ones(1008)

        with pytest.raises(TypeError) as e_info:
            waveform[0] = 1
        with pytest.raises(RuntimeError) as e_info:
            waveform[0] = wave1
        with pytest.raises(RuntimeError) as e_info:
            waveform[0] = wave1
        with pytest.raises(RuntimeError) as e_info:
            waveform[0] = (wave1, wave2, wave3, marker)

        # "standart" waveform
        waveform[0] = (wave1, wave2)
        assert waveform[0] == (wave1, wave2, None)
        assert len(waveform.get_raw_vector(0)) == 1008 * 2

        # replace wave
        waveform[0] = (wave1, wave3)
        assert waveform[0] == (wave1, wave3, None)

        # replace wave
        waveform.assign_waveform(0, wave1, wave2)
        assert waveform[0] == (wave1, wave2, None)

        # delete wave
        assert 0 in waveform.keys()
        del waveform[0]
        assert 0 not in waveform.keys()

        # iter
        waveform[0] = (wave1, wave3)
        waveform[2] = (wave1, wave3)
        waveform[10] = (wave1, wave3)
        assert len(waveform) == 3
        num_elements = 0
        for _, element in waveform.items():
            assert all(element[0] == wave1)
            assert all(element[1] == wave3)
            num_elements += 1
        assert num_elements == len(waveform)

        # add zero_padding
        waveform[0] = (wave1_short, wave2_short)
        raw_waveform = waveform.get_raw_vector(0, target_length=1000)
        assert len(raw_waveform) == 2000
        assert raw_waveform[-1] == 0
        assert raw_waveform[-1000] == 0
        assert raw_waveform[0] != 0
        assert raw_waveform[1000 - 1] != 0
        assert "waveforms are smaller than the target length" in caplog.messages[-1]

        waveform[0] = (wave1_short, wave2_short)
        waveform.zero_padding(0, at_the_end=False)
        raw_waveform = waveform.get_raw_vector(0, target_length=1000)
        assert len(raw_waveform) == 2000
        assert raw_waveform[-1] != 0
        assert raw_waveform[-1000] != 0
        assert raw_waveform[0] == 0
        assert raw_waveform[1000 - 1] == 0

        # default does not change specfic configuration
        waveform[0] = (wave1_short, wave2_short)
        waveform.zero_padding(at_the_end=True)
        raw_waveform = waveform.get_raw_vector(0, target_length=1000)
        assert len(raw_waveform) == 2000
        assert raw_waveform[-1] != 0
        assert raw_waveform[-1000] != 0
        assert raw_waveform[0] == 0
        assert raw_waveform[1000 - 1] == 0

        # clamp
        raw_waveform = waveform.get_raw_vector(0, target_length=100)
        assert len(raw_waveform) == 200

        # "standart" waveform with marker
        waveform[1] = (wave1, wave2, marker)
        assert waveform[1] == (wave1, wave2, marker)
        assert len(waveform.get_raw_vector(1)) == 1008 * 3

        # unequal length
        with pytest.raises(RuntimeError) as e_info:
            waveform[10] = (wave1_short, wave2)
        with pytest.raises(RuntimeError) as e_info:
            waveform[10] = (wave1, wave2, wave1_short)

    def test_write_to_waveform_memory(self, data_dir, mock_connection, awg_module):

        json_path = data_dir / "waveform_descriptors.json"
        with json_path.open("r", encoding="UTF-8") as file:
            waveform_descriptiors = file.read()
        mock_connection.return_value.get.return_value = OrderedDict(
            [
                (
                    "/dev12044/sgchannels/0/awg/waveform/descriptors",
                    [
                        {
                            "timestamp": 1158178198389432,
                            "flags": 0,
                            "vector": waveform_descriptiors,
                        }
                    ],
                )
            ]
        )
        waveforms = Waveforms()
        wave1 = 1.0 * np.ones(1008)
        wave2 = -1.0 * np.ones(1008)
        marker = np.zeros(1008)
        waveforms[0] = (wave1, wave2)
        waveforms[1] = (wave1, wave2, marker)
        awg_module.write_to_waveform_memory(waveforms)
        assert (
            mock_connection.return_value.set.call_args[0][0][0][0]
            == "/dev1234/sgchannels/0/awg/waveform/waves/0"
        )
        assert (
            mock_connection.return_value.set.call_args[0][0][1][0]
            == "/dev1234/sgchannels/0/awg/waveform/waves/1"
        )
        assert all(
            mock_connection.return_value.set.call_args[0][0][0][1]
            == waveforms.get_raw_vector(0)
        )
        assert all(
            mock_connection.return_value.set.call_args[0][0][1][1]
            == waveforms.get_raw_vector(1)
        )

        # to big index
        waveforms[10] = (wave1, wave2)
        with pytest.raises(IndexError) as e_info:
            awg_module.write_to_waveform_memory(waveforms)
        del waveforms[10]
        # assign to filler
        waveforms[2] = (wave1, wave2)
        with pytest.raises(RuntimeError) as e_info:
            awg_module.write_to_waveform_memory(waveforms)

    def test_read_from_waveform_memory(self, data_dir, mock_connection, awg_module):
        json_path = data_dir / "waveform_descriptors.json"
        with json_path.open("r", encoding="UTF-8") as file:
            waveform_descriptiors = json.loads(file.read())

        single_wave_result = []
        def get_side_effect(nodes, **kwargs):
            if nodes.lower() == "/dev1234/sgchannels/0/awg/waveform/descriptors":
                return OrderedDict(
                    [
                        (
                            "/dev1234/sgchannels/0/awg/waveform/descriptors",
                            [
                                {
                                    "timestamp": 1158178198389432,
                                    "flags": 0,
                                    "vector": json.dumps(waveform_descriptiors),
                                }
                            ],
                        )
                    ]
                )
            if "/dev1234/sgchannels/0/awg/waveform/waves/" in nodes.lower():
                if nodes[-1] == "*":
                    return OrderedDict(
                        [
                            (
                                "/dev1234/sgchannels/0/awg/waveform/waves/0",
                                [
                                    {
                                        "timestamp": 338544371667920,
                                        "flags": 0,
                                        "vector": zi_utils.convert_awg_waveform(
                                            np.ones(1008), -np.ones(1008), np.ones(1008)
                                        ),
                                    }
                                ],
                            ),
                            (
                                "/dev1234/sgchannels/0/awg/waveform/waves/1",
                                [
                                    {
                                        "timestamp": 338544371667920,
                                        "flags": 0,
                                        "vector": [],
                                    }
                                ],
                            ),
                            (
                                "/dev1234/sgchannels/0/awg/waveform/waves/2",
                                [
                                    {
                                        "timestamp": 338544371667920,
                                        "flags": 0,
                                        "vector": [],
                                    }
                                ],
                            ),
                        ]
                    )
                else:
                    return OrderedDict(
                        [
                            (
                                f"/dev1234/sgchannels/0/awg/waveform/waves/{nodes[-1]}",
                                [
                                    {
                                        "timestamp": 338544371667920,
                                        "flags": 0,
                                        "vector": single_wave_result,
                                    }
                                ],
                            )
                        ]
                    )
            raise RuntimeError()

        mock_connection.return_value.get.side_effect = get_side_effect
        waveforms = awg_module.read_from_waveform_memory()
        assert all(waveforms[0][0] == np.ones(1008))
        assert all(waveforms[0][1] == -np.ones(1008))
        assert all(waveforms[0][2] == np.ones(1008))
        assert all(waveforms[1][0] == np.ones(0))
        assert all(waveforms[1][1] == np.ones(0))
        assert all(waveforms[1][2] == np.ones(0))

        # single Node Acces
        single_wave_result = zi_utils.convert_awg_waveform(
            np.ones(1008), -np.ones(1008), np.ones(1008)
        )
        waveforms = awg_module.read_from_waveform_memory([0])
        assert len(waveforms) == 1
        assert all(waveforms[0][0] == np.ones(1008))
        assert all(waveforms[0][1] == -np.ones(1008))
        assert all(waveforms[0][2] == np.ones(1008))

        single_wave_result = zi_utils.convert_awg_waveform(
            np.ones(1008), -np.ones(1008), None
        )
        waveform_descriptiors["waveforms"][1]["marker_bits"] = "0;0"
        waveforms = awg_module.read_from_waveform_memory([1])
        assert len(waveforms) == 1
        assert all(waveforms[1][0] == np.ones(1008))
        assert all(waveforms[1][1] == -np.ones(1008))
        assert waveforms[1][2] == None

        single_wave_result = zi_utils.convert_awg_waveform(
            np.ones(1008), None, np.ones(1008)
        )
        waveform_descriptiors["waveforms"][1]["channels"] = "1"
        waveform_descriptiors["waveforms"][1]["marker_bits"] = "1;0"
        waveforms = awg_module.read_from_waveform_memory([1])
        assert len(waveforms) == 1
        assert all(waveforms[1][0] == np.ones(1008))
        assert waveforms[1][1] == None
        assert all(waveforms[1][2] == np.ones(1008))

        single_wave_result = zi_utils.convert_awg_waveform(
            np.ones(1008), None, None
        )
        waveform_descriptiors["waveforms"][1]["channels"] = "1"
        waveform_descriptiors["waveforms"][1]["marker_bits"] = "0;0"
        waveforms = awg_module.read_from_waveform_memory([1])
        assert len(waveforms) == 1
        assert all(waveforms[1][0] == np.ones(1008))
        assert waveforms[1][1] == None
        assert waveforms[1][2] == None
