import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfqa
from zhinst.toolkit.driver.modules.generator import Generator
from zhinst.toolkit import SHFQAWaveforms


@pytest.fixture()
def generator(data_dir, mock_connection, session, shfqa):

    json_path = data_dir / "nodedoc_awg_test.json"
    with json_path.open("r", encoding="UTF-8") as file:
        nodes_json = file.read()
    mock_connection.return_value.awgModule.return_value.listNodesJSON.return_value = (
        nodes_json
    )

    yield Generator(shfqa, session, ("qachannels", "0", "generator"), 0)


class TestGenerator:
    def test_wait_done(self, mock_connection, generator):
        single = 0
        enable = iter([])

        def get_int_side_effect(node):
            if node.upper() == "/DEV1234/QACHANNELS/0/GENERATOR/SINGLE":
                return single
            if node.upper() == "/DEV1234/QACHANNELS/0/GENERATOR/ENABLE":
                return next(enable)

        mock_connection.return_value.getInt.side_effect = get_int_side_effect

        # if not single mode this function throws a RuntimeError
        with pytest.raises(RuntimeError) as e_info:
            generator.wait_done()

        # already finished
        single = 1
        enable = iter([0] * 2)
        generator.wait_done()
        # finishes in time
        single = 1
        enable = iter([1] * 3 + [0] * 2)
        generator.wait_done()
        # don't finish
        single = 1
        enable = cycle([1])
        with pytest.raises(TimeoutError) as e_info:
            generator.wait_done(timeout=0.1)

    def test_load_sequencer_program(self, session, generator, mock_connection):
        with patch(
            "zhinst.toolkit.driver.modules.generator.deviceutils", autospec=True
        ) as deviceutils:
            generator.load_sequencer_program("Test")
            deviceutils.load_sequencer_program.assert_called_once_with(
                mock_connection.return_value,
                "DEV1234",
                0,
                "Test",
                session.awg_module,
                timeout=10,
            )

            generator.load_sequencer_program("Test", timeout = 1)
            deviceutils.load_sequencer_program.assert_called_with(
                mock_connection.return_value,
                "DEV1234",
                0,
                "Test",
                session.awg_module,
                timeout=1,
            )

    def test_waveforms(self):
        waveforms = SHFQAWaveforms()
        assert len(waveforms) == 0

        waveforms[0] = np.zeros(100)
        waveforms[1] = 2*np.ones(100)
        waveforms[100] = np.ones(100)

        assert len(waveforms) == 3

        assert all(waveforms[0] == np.zeros(100).astype(complex))
        assert all(waveforms[1] == np.ones(100).astype(complex))
        assert all(waveforms[1] == waveforms[100])
        del waveforms[100]
        assert len(waveforms) == 2

        # empty lists will me converted to 0
        waveforms[1] = []
        assert waveforms[1] == np.zeros(1).astype(complex)


    def test_write_to_waveform_memory(self, session, generator, mock_connection):

        waveforms = SHFQAWaveforms()
        waveforms_long = SHFQAWaveforms()
        waveforms_long[1000] = np.zeros(1000)
        with patch(
            "zhinst.toolkit.driver.modules.generator.deviceutils", autospec=True
        ) as deviceutils:
            generator.write_to_waveform_memory(waveforms)
            deviceutils.write_to_waveform_memory.assert_called_once_with(
                mock_connection.return_value,
                "DEV1234",
                0,
                waveforms,
                clear_existing=True,
            )

            generator.write_to_waveform_memory(waveforms, clear_existing = False)
            deviceutils.write_to_waveform_memory.assert_called_with(
                mock_connection.return_value,
                "DEV1234",
                0,
                waveforms,
                clear_existing=False,
            )
        with pytest.raises(RuntimeError) as e_info:
            generator.write_to_waveform_memory(waveforms_long)
