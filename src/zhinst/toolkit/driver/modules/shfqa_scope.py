# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

import logging
from typing import List
from zhinst.toolkit.nodetree import Node
import zhinst.deviceutils.shfqa as deviceutils

logger = logging.getLogger(__name__)


class SHFScope(Node):
    """SHF Scope"""

    def __init__(self, device: "SHFQA", session, tree):
        super().__init__(device.root, tree)
        self._device = device
        self._serial = device.serial
        self._session = session

    def run(self, single: bool = True, timeout: float = 10, sleep_time: float = 0.005):
        """Stop the scope recording.

        Arguments:
            timeout (int): The maximum waiting time in seconds for the
                Scope (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting the progress and records values
        """

        self.single(single)
        self.enable(True)
        if not self.enable.wait_for_state_change(
            1, timeout=timeout, sleep_time=sleep_time
        ):
            raise TimeoutError(
                "Scope could not been started within the "
                f"specified timeout({timeout}."
            )

    def stop(self, timeout: float = 10, sleep_time: float = 0.005) -> None:
        """Stop the scope recording.

        Arguments:
            timeout (int): The maximum waiting time in seconds for the
                Scope (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting the progress and records values
        """
        self.enable(False)
        if not self.enable.wait_for_state_change(
            0, timeout=timeout, sleep_time=sleep_time
        ):
            raise TimeoutError(
                "Scope could not been stoped within the "
                f"specified timeout({timeout}."
            )

    def wait_done(self, timeout: float = 10, sleep_time: float = 0.005) -> None:
        """Wait until the Scope recording is finished.

        Arguments:
            timeout (int): The maximum waiting time in seconds for the
                Scope (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting the progress and records values

        Raises:
            ToolkitError: If the Scope recording is not done before the
                timeout.

        """
        if not self.enable.wait_for_state_change(
            0, timeout=timeout, sleep_time=sleep_time
        ):
            raise TimeoutError(
                "Scope recording did not finish within the "
                f"specified timeout({timeout}."
            )

    @property
    def available_trigger_inputs(self) -> List[str]:
        """List the available trigger sources for the scope."""
        return [key for key in self.trigger.channel.options.keys()]

    @property
    def available_inputs(self) -> List[str]:
        """List the available signal sources for the scope channels."""
        return [key for key in self.channels[0].inputselect.options.keys()]

    def configure(
        self,
        input_select:dict,
        num_samples: int,
        trigger_input : str,
        num_segments: int = 1,
        num_averages: int = 1,
        trigger_delay: int = 0,
    ) -> None:
        """Configures the scope for a measurement.

        Args:
            input_select (dict): keys (int) map a specific scope channel with a
                signal source (str), e.g. "channel0_signal_input". For a list of
                available values use `available_inputs`
            num_samples (int): number samples to recorded in a scope shot.
            trigger_input (str): specifies the trigger source of the scope
                acquisition - if set to None, the self-triggering mode of the
                scope becomes active, which is useful e.g. for the GUI.
                For a list of available trigger values use
                `available_trigger_inputs`
            num_segments (int): number of distinct scope shots to be returned
                after ending the acquisition
            num_averages (int): specifies how many times each segment should be
                averaged on hardware; to finish a scope acquisition, the number
                of issued triggers must be equal to num_segments * num_averages
            trigger_delay (int): delay in samples specifying the time between
                the start of data acquisition and reception of a trigger
    """
        deviceutils.configure_scope(
            self._session.daq_server,
            self._serial,
            input_select,
            num_samples,
            trigger_input,
            num_segments,
            num_averages,
            trigger_delay,
        )

    def read(
        self,
        channel=None,
        timeout: float = 10,
    ) -> tuple:
        """Read out the recorded data from the specified channel of the scope.

        Arguments:
            channel (int): The scope channel to read the data from. If
                no channel is specified, the method will return the data
                for all channels.
            blocking (bool): A flag that specifies if the program
                should be blocked until the scope has finished
                recording (default: True).
            timeout (float): The maximum waiting time in seconds for the
                Scope (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting the progress and records values

        Returns:
            (recorded_data, recorded_data_range, scope_time).

        Raises:
            TimeoutError: if the scope recording is not completed before
                timeout.

        """
        recorded_data, recorded_data_range, scope_time = deviceutils.get_scope_data(
            self._session.daq_server, self._serial, timeout
        )

        # TODO optimize if channel is not None
        if channel is not None:
            return (
                recorded_data[channel],
                recorded_data_range[channel],
                scope_time[channel],
            )
        return (
            recorded_data,
            recorded_data_range,
            scope_time,
        )
