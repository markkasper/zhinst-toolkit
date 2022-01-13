import pytest
from itertools import cycle
from unittest.mock import patch
import numpy as np
from fixtures import mock_connection, data_dir, session, shfqa
from zhinst.toolkit import MappingMode, AveragingMode, TriggerImpedance
from zhinst.toolkit.driver.modules.shfqa_sweeper import (
    SHFSweeper,
    RfConfig,
    TriggerConfig,
    SweepConfig,
    AvgConfig,
)


@pytest.fixture()
def core_sweeper():
    with patch(
        "zhinst.toolkit.driver.modules.shfqa_sweeper.CoreSweeper", autospec=True
    ) as core_sweeper:
        yield core_sweeper


@pytest.fixture()
def sweeper(session, shfqa, core_sweeper):
    yield SHFSweeper(shfqa, session, 0)


class TestSHFSweeper:
    def test_repr(self, sweeper):
        assert repr(sweeper) == "Sweeper Module for QAChannel 0"

    def test_run(self, mock_connection, sweeper, core_sweeper):
        def getDouble_side_effect(node):
            if node == "/DEV1234/QACHANNELS/0/INPUT/RANGE":
                return 10
            if node == "/DEV1234/QACHANNELS/0/OUTPUT/RANGE":
                return 20
            if node == "/DEV1234/QACHANNELS/0/CENTERFREQ":
                return 30
            if node == "/DEV1234/QACHANNELS/0/OSCS/0/GAIN":
                return 40
            if node == "/DEV1234/QACHANNELS/0/SPECTROSCOPY/LENGTH":
                return 100.0
            return RuntimeError("Undefined Node")

        def getInt_side_effect(node):
            if node == "/DEV1234/QACHANNELS/0/SPECTROSCOPY/TRIGGER/CHANNEL":
                return 10
            raise RuntimeError("Undefined Node")

        mock_connection.return_value.getDouble.side_effect = getDouble_side_effect
        mock_connection.return_value.getInt.side_effect = getInt_side_effect

        sweeper.run()
        core_sweeper.return_value.run.assert_called_once()
        # TODO test single update calls

        core_sweeper.return_value.configure.assert_any_call(
            rf_config=RfConfig(
                channel=0, input_range=10, output_range=20, center_freq=30
            )
        )
        core_sweeper.return_value.configure.assert_any_call(
            trig_config=TriggerConfig(source=10, level=0.5, imp50=True)
        )
        core_sweeper.return_value.configure.assert_any_call(
            sweep_config=SweepConfig(
                start_freq=-300000000.0,
                stop_freq=300000000.0,
                num_points=100,
                mapping="linear",
                oscillator_gain=40,
            )
        )
        core_sweeper.return_value.configure.assert_any_call(
            avg_config=AvgConfig(
                integration_time=5e-8,
                num_averages=1,
                mode="cyclic",
                integration_delay=0.0,
            )
        )

    def test_get_result(self, sweeper, core_sweeper):
        sweeper.get_result()
        core_sweeper.return_value.get_result.assert_called_once()

    def test_plot(self, sweeper, core_sweeper):
        sweeper.plot()
        core_sweeper.return_value.plot.assert_called_once()

    def test_output_freq(self, mock_connection, sweeper):
        def getDouble_side_effect(node):
            if node == "/DEV1234/QACHANNELS/0/CENTERFREQ":
                return 33
            if node == "/DEV1234/QACHANNELS/0/OSCS/0/FREQ":
                return 44
            raise RuntimeError("Undefined Node")

        mock_connection.return_value.getDouble.side_effect = getDouble_side_effect
        output_freq = sweeper.output_freq
        assert output_freq == 33 + 44

    def test_integration_delay(self, shfqa, sweeper):
        assert shfqa.qachannels[0].spectroscopy.delay == sweeper.integration_delay

    def test_properties(self, mock_connection, core_sweeper, sweeper):
        def getDouble_side_effect(node):
            if node == "/DEV1234/QACHANNELS/0/INPUT/RANGE":
                return 10
            if node == "/DEV1234/QACHANNELS/0/OUTPUT/RANGE":
                return 20
            if node == "/DEV1234/QACHANNELS/0/CENTERFREQ":
                return 30
            if node == "/DEV1234/QACHANNELS/0/OSCS/0/GAIN":
                return 40
            if node == "/DEV1234/QACHANNELS/0/SPECTROSCOPY/LENGTH":
                return 100.0
            return RuntimeError("Undefined Node")

        def getInt_side_effect(node):
            if node == "/DEV1234/QACHANNELS/0/SPECTROSCOPY/TRIGGER/CHANNEL":
                return 10
            raise RuntimeError("Undefined Node")

        mock_connection.return_value.getDouble.side_effect = getDouble_side_effect
        mock_connection.return_value.getInt.side_effect = getInt_side_effect

        # trigger_level
        assert sweeper.trigger_level == 0.5
        sweeper.trigger_level = 1
        assert sweeper.trigger_level == 1
        core_sweeper.return_value.configure.assert_called_once_with(
            trig_config=TriggerConfig(source=10, level=1, imp50=True)
        )

        # trigger_impedance
        assert sweeper.trigger_impedance == TriggerImpedance.OHM50
        sweeper.trigger_impedance = TriggerImpedance.OHM1K
        assert sweeper.trigger_impedance == TriggerImpedance.OHM1K
        core_sweeper.return_value.configure.assert_called_with(
            trig_config=TriggerConfig(source=10, level=1, imp50=False)
        )

        # start_frequency
        assert sweeper.start_frequency == -300e6
        sweeper.start_frequency = -200e6
        assert sweeper.start_frequency == -200e6
        core_sweeper.return_value.configure.assert_any_call(
            sweep_config=SweepConfig(
                start_freq=-200000000.0,
                stop_freq=300000000.0,
                num_points=100,
                mapping="linear",
                oscillator_gain=40,
            )
        )

        # stop_frequency
        assert sweeper.stop_frequency == 300e6
        sweeper.stop_frequency = 200e6
        assert sweeper.stop_frequency == 200e6
        core_sweeper.return_value.configure.assert_any_call(
            sweep_config=SweepConfig(
                start_freq=-200000000.0,
                stop_freq=200000000.0,
                num_points=100,
                mapping="linear",
                oscillator_gain=40,
            )
        )

        # num_points
        assert sweeper.num_points == 100
        sweeper.num_points = 500
        assert sweeper.num_points == 500
        core_sweeper.return_value.configure.assert_any_call(
            sweep_config=SweepConfig(
                start_freq=-200000000.0,
                stop_freq=200000000.0,
                num_points=500,
                mapping="linear",
                oscillator_gain=40,
            )
        )

        # mapping
        assert sweeper.mapping == MappingMode.LIN
        sweeper.mapping = MappingMode.LOG
        assert sweeper.mapping == MappingMode.LOG
        core_sweeper.return_value.configure.assert_any_call(
            sweep_config=SweepConfig(
                start_freq=-200000000.0,
                stop_freq=200000000.0,
                num_points=500,
                mapping="log",
                oscillator_gain=40,
            )
        )

        # num_averages
        assert sweeper.num_averages == 1
        sweeper.num_averages = 34
        assert sweeper.num_averages == 34
        core_sweeper.return_value.configure.assert_any_call(
            avg_config=AvgConfig(
                integration_time=5e-8,
                num_averages=34,
                mode="cyclic",
                integration_delay=0.0,
            )
        )

        # averaging_mode
        assert sweeper.averaging_mode == AveragingMode.CYCLIC
        sweeper.averaging_mode = AveragingMode.SEQUENTIAL
        assert sweeper.averaging_mode == AveragingMode.SEQUENTIAL
        core_sweeper.return_value.configure.assert_any_call(
            avg_config=AvgConfig(
                integration_time=5e-8,
                num_averages=34,
                mode="sequential",
                integration_delay=0.0,
            )
        )
