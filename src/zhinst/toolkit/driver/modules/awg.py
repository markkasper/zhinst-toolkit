# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

""" Zurich Instruments Toolkit (zhinst-toolkit) AWG Module."""
from typing import Optional
import time
import logging
from collections.abc import MutableMapping
import numpy as np
import json
import zhinst.utils as zi_utils
from zhinst.toolkit.helper import lazy_property
from zhinst.toolkit.driver.modules.command_table import CommandTable
from zhinst.toolkit.nodetree import Node

logger = logging.getLogger(__name__)


class Waveforms(MutableMapping):
    """Waveform dictionary

    The key specifies the slot of the waveform on the device.
    The value is a the waveform itself, represented by a tuple
    (wave1, wave2, marker).
    The value tuple(wave1, wave2, marker=None) consists of the follwing parts:
        * wave1 (array): Array with data of waveform 1.
        * wave2 (array): Array with data of waveform 2.
        * markers (array): Array with marker data.

    A helper function exist called `assign_waveform` which provides an easy way
    of assigning waveforms to slots. But one can also use the direct dictionary
    access:
    >>> wave = 1.0 * np.ones(1008)
    >>> markers = np.zeros(1008)
    >>> waveforms = Waveforms()
    >>> waveforms.assign_waveform(0, wave)
    >>> waveforms.assign_waveform(1, wave, -wave)
    >>> waveforms.assign_waveform(2, wave, -wave, markers)
    >>> waveforms.assign_waveform(3, wave, markers=markers)
    >>> waveforms[4] = (wave,)
    >>> waveforms[5] = (wave, -wave)
    >>> waveforms[6] = (wave, -wave, markers)
    >>> waveforms[7] = (wave, None, markers)

    The arrays can be provided as arrays of interger or floats. The function
    `get_raw_vector` is used to convert a waveform into a native AWG
    waveform format (interleaved waves and markers as uint16) that can be uploaded
    to the waveform node. The function also rescales the waves and marker to the
    range [-1,1].

    The function `get_raw_vector` also takes an optional keyword argument called
    `target_length`. If specfied the waves and marker will be clamped or zero
    padded to match that value. By default the zero padding adds zeros to the
    end of the vector. With the function `zero_padding` this behaviour can be
    changed.
    """

    def __init__(self):
        self._waveforms = {}
        self._padding_start = {}
        self._padding_default = None

    def __getitem__(self, slot: int):
        return self._waveforms[slot]

    def assign_waveform(self, slot: int, wave1, wave2=None, markers=None) -> None:
        """Assigns a waveform to a slot.

        Args:
            slot (int): slot number
            wave1 (array): Array with data of waveform 1.
            wave2 (array): Array with data of waveform 2. (default = None)
            markers (array): Array with marker data. (default = None)
        """
        self._waveforms[slot] = (wave1, wave2, markers)

    def assign_native_awg_waveform(
        self, slot: int, raw_waveform, channels:int=1, markers_present:bool=False
    )-> None:
        """Assigns a native AWG waveform to a slot.

        By native AWG waveform a single waveform (interleaved waves and markers
        as uint16) is meant.

        Args:
            slot (int): slot number
            raw_waveform (array): native AWG waveform.
            channels (int): Number of channels present in the wave.
                (default = 1)
            markers (bool): Indicates if markers are interleaved in the wave.
                (default = False)
        """
        wave1, wave2, markers = zi_utils.parse_awg_waveform(
            raw_waveform,
            channels=channels,
            markers_present=markers_present,
        )
        if markers_present and channels == 2:
            self._waveforms[slot] = (wave1, wave2, markers)
        elif channels == 2:
            self._waveforms[slot] = (wave1, wave2, None)
        elif markers_present:
            self._waveforms[slot] = (wave1, None, markers)
        else:
            self._waveforms[slot] = (wave1, None, None)

    def __setitem__(self, slot: int, value: tuple):
        if len(value) < 1 or len(value) > 3:
            raise RuntimeError(
                "Only one or two waveforms (plus an optional marker) can be specified "
                f"per Waveform. ({len(value)} where specified."
            )
        if len(value) >= 2 and value[1] is not None and len(value[0]) != len(value[1]):
            raise RuntimeError("The two waves must have the same length")
        if len(value) == 3 and value[2] is not None and len(value[0]) != len(value[2]):
            raise RuntimeError(
                "The marker must have the same length than the waveforms"
            )
        self._waveforms[slot] = value + (None,) * (3 - len(value))

    def __delitem__(self, slot: int):
        del self._waveforms[slot]

    def __iter__(self):
        return iter(self._waveforms)

    def __len__(self):
        return len(self._waveforms)

    def zero_padding(self, slot: int = -1, at_the_end=True) -> None:
        """Specfies if the zero padding behaviour

        If no slot is specfied (slot=-1) the default value is changed. This
        means that the specfied behaviour is applied to all waveforms in this
        dictionary (during the conversion).

        WARNING: Changing the default values does not affect slots for which a
            specific behaviour has been set (with this function).

        Args:
            slot (int): Slot of which the zero padding behaviour should be
                changed. If -1 the default value for all slots is changed.
                (default = -1)
            at_the_end (bool): Flag if the zerro padding should be done at the
                end of the arrays. (default = True)
        """
        if slot == -1:
            self._padding_default = not at_the_end
        else:
            self._padding_start[slot] = not at_the_end

    @staticmethod
    def _perpare_wave(
        wave,
        max_wave: float,
        target_length: int,
        padding_start: bool,
        warn_clamping: bool,
        warn_padding: bool,
    ):
        """Prepares as single wave for conversion.

        Clamps or zeropads the length and rescale the amplitude to
        -1 <= abs(wave) <= 1.

        Args:
            wave (array): input wave
            max_wave: (float): maximum value of the wave
            target_length (int): target length of the rsulting wave
            padding_start (bool): Flag if the zeros should be padded at the
                beginning or end
            warn_clamping (bool): Flag if a log warning should be issued if
                clamping is performed
            warn_padding (bool): Flag if a log warning should be issued if zero
                padding is performed

        Returns:
            array: processed wave
        """
        if len(wave) >= target_length:
            if warn_clamping and len(wave) > target_length:
                logger.warning(
                    f"waveforms are larger than the target length "
                    f"{len(wave)} > {target_length}. They will be clamped to the "
                    "target length"
                )
            wave = (
                wave[:target_length] / max_wave
                if max_wave > 1
                else wave[:target_length]
            )
        else:
            wave = wave / max_wave if max_wave > 1 else wave
            if not padding_start:
                if warn_padding:
                    logger.warning(
                        f"waveforms are smaller than the target length "
                        f"{len(wave)} < {target_length}. Zeros will be added to the "
                        "end of the waveform to match the target length. "
                        "(Use Waveforms.zero_padding to change the default or to "
                        "avoid this warning)"
                    )
                wave = np.concatenate((wave, np.zeros(target_length - len(wave))))
            else:
                wave = np.concatenate((np.zeros(target_length - len(wave)), wave))
        return wave

    def get_raw_vector(self, slot: int, target_length: int = None):
        """Converts a waveform into the native AWG waveform format

        The conversion consists of the follwoing points:
            * The waves and markers are clamps or zeropads to match the
              `target_length` (if specified)
            * The waves and markers are rescaled to -1 <= abs(wave) <= 1 (if
              it is outside of these bounds)
            * The waves and markers are conerted into a single array of the
              native AWG waveform format (interleaved waves and markers as
              uint16).

        Args:
            slot (int): slot number of the waveform
            target_length (int): target length of the output waveform. If
                specified the waves and markers will have the specified length
                (e.g. wave1, wave2 and markers are specified the resulting
                waveform will have the length 3*target_length). (default = None)

        Returns:
            array: waveform in the native AWG format
        """
        # TODO add csv import
        x = self._waveforms[slot]
        x1 = np.zeros(1) if len(x[0]) == 0 else x[0]
        x2 = np.zeros(1) if x[1] is not None and len(x[1]) == 0 else x[1]
        marker = x[2]

        padding_start = self._padding_start.get(slot, self._padding_default)
        target_length = len(x1) if target_length is None else target_length

        return zi_utils.convert_awg_waveform(
            self._perpare_wave(
                x1,
                np.max(np.abs(x1)),
                target_length,
                padding_start,
                True,
                self._padding_default is None or slot not in self._padding_start,
            ),
            wave2=self._perpare_wave(
                x2,
                np.max(np.abs(x2)),
                target_length,
                padding_start,
                False,  # warning done with the first wave
                False,  # warning done with the first wave
            ),
            markers=self._perpare_wave(
                marker,
                1,
                target_length,
                padding_start,
                False,  # warning done with the first wave
                False,  # warning done with the first wave
            )
            if marker is not None
            else None,
        )


class AWGModule(Node):
    """Abstract AWG Module.

    This module implements the basic functionality for the device specific
    arbitrary waveform generator.
    Besides the upload/compilation of sequences it offers the upload of waveforms
    and command tables.

    Arguments:
    module (:class: `AWGModuleConnection`) ziPython AWG module.
    connection (:class: `ZIConnection`): Connection Object of the device.
    ct_node (Optional[Node]): node for the command table upload
    ct_schema_url (Optional[str]): url for the command table validation schema
    """

    def __init__(
        self,
        device,
        session,
        tree,
        index: int,
        ct_schema_url: Optional[str] = None,
    ):
        Node.__init__(self, device.root, tree)
        self._session = session
        self._device = device
        self._serial = device.serial
        self._index = index
        self._ct_schema_url = ct_schema_url
        self._ct = None
        self._sequence = None
        self._waveforms = []

    def wait_done(self, timeout: float = 10, sleep_time: float = 0.005) -> None:
        """Wait until the AWG is finished.

        Arguments:
            timeout (float): The maximum waiting time in seconds for the
                generator (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting generator state

        Raises:
            RuntimeError: If continuous mode is enabled
            TimeoutError: If the sequencer program did not finish within the timout
        """
        if not self.single():
            raise RuntimeError(
                f"{repr(self)}: The generator is running in continuous mode, "
                "it will never be finished."
            )
        if not self.enable.wait_for_state_change(
            0, timeout=timeout, sleep_time=sleep_time
        ):
            raise TimeoutError(
                f"{repr(self)}: The exceution of the sequencer program did not finish "
                f"within the specified timeout ({timeout}s)."
            )

    def load_sequencer_program(
        self, sequencer_program: str, timeout: float = 100.0
    ) -> None:
        """Compiles the current SequenceProgram on the AWG Core.

        Raises:
            ToolkitConnectionError: If the AWG Core has not been set up
                yet
            ToolkitError: if the compilation has failed or the ELF
                upload is not successful.
            TimeoutError: if the program upload is not completed before
                timeout.
        """
        awg = self._session.awg_module.nodetree
        awg.device(self._serial)
        awg.index(self._index)
        self._session.awg_module.execute()
        logger.info(f"{repr(self)}: Compiling sequencer program")
        awg.compiler.sourcestring(sequencer_program)
        compiler_status = awg.compiler.status()
        start = time.time()
        while compiler_status == -1:
            if time.time() - start >= timeout:
                logger.critical(f"{repr(self)}: Program compilation timed out")
                raise TimeoutError(f"{repr(self)}: Program compilation timed out")
            time.sleep(0.1)
            compiler_status = awg.compiler.status()

        if compiler_status == 1:
            logger.critical(
                f"{repr(self)}: Error during sequencer compilation"
                f"{awg.compiler.statusstring()}"
            )
            raise RuntimeError(
                f"{repr(self)}: Error during sequencer compilation."
                "Check the log for detailed information"
            )
        elif compiler_status == 2:
            logger.warning(
                f"{repr(self)}: Warning during sequencer compilation"
                f"{awg.compiler.statusstring()}"
            )
        elif compiler_status == 0:
            logger.info(f"{repr(self)}: Compilation successful")

        progress = awg.progress()
        logger.info(f"{repr(self)}: Uploading ELF file to device")
        while progress < 1.0 and awg.elf.status() == 2 and self.ready() == 0:
            if time.time() - start >= timeout:
                logger.critical(f"{repr(self)}: Program upload timed out")
                raise TimeoutError(f"{repr(self)}: Program upload timed out")
            print(f"{repr(self)}: {progress*100}%")
            time.sleep(0.1)
            progress = awg.progress()

        if awg.elf.status() == 0 and self.ready():
            logger.info(f"{repr(self)}: ELF file uploaded")
        else:
            logger.critical(
                f"{repr(self)}: Error during upload of ELF file"
                f"(with status {awg.elf.status()}"
            )
            raise RuntimeError(
                f"{repr(self)}: Error during upload of ELF file."
                "Check the log for detailed information"
            )

    def write_to_waveform_memory(self, waveforms: Waveforms) -> None:
        """Writes waveforms to the waveform memory.

        The waveforms must already be assigned in the sequencer programm.

        Args:
            waveforms (Waveforms): Waveforms that should be uploaded.

        Raises:
            IndexError: The index of a waveform exeeds the one on the device
            RuntimeError: One of the waveforms index points to a filler(placeholder)
        """
        waveform_info = json.loads(self.waveform.descriptors()).get("waveforms", [])
        num_waveforms = len(waveform_info)
        commands = []
        for waveform_index in waveforms.keys():
            if waveform_index >= num_waveforms:
                raise IndexError(
                    f"There are {num_waveforms} waveforms defined "
                    "on the device but the passed waveforms specified one with index "
                    f"{waveform_index}."
                )
            if "__filler" in waveform_info[waveform_index]["name"]:
                raise RuntimeError(
                    f"The waveform at index {waveform_index} is only "
                    "a filler and can not be overwritten"
                )

            commands.append(
                (
                    self.waveform.node + f"/waves/{waveform_index}",
                    waveforms.get_raw_vector(
                        waveform_index,
                        target_length=int(waveform_info[waveform_index]["length"]),
                    ),
                )
            )
        self._session.daq_server.set(commands)

    def read_from_waveform_memory(self, indexes: list = None) -> Waveforms:
        waveform_info = json.loads(self.waveform.descriptors()).get("waveforms", [])
        nodes = []
        if indexes is not None:
            for index in indexes:
                nodes.append(self.waveform.node + f"/waves/{index}")
        else:
            nodes.append(self.waveform.node + "/waves/*")
        nodes = ",".join(nodes)
        waveforms_raw = self._session.daq_server.get(
            nodes, settingsonly=False, flat=True
        )
        waveforms = Waveforms()
        for node, waveform in waveforms_raw.items():
            slot = int(node[-1])
            if not "__filler" in waveform_info[slot]["name"]:
                waveforms.assign_native_awg_waveform(
                    slot,
                    waveform[0]["vector"],
                    channels=int(waveform_info[slot].get("channels", 1)),
                    markers_present=bool(int(waveform_info[slot].get("marker_bits")[0])),
                )
        return waveforms

    @lazy_property
    def commandtable(self) -> CommandTable:
        """Command table module."""
        return CommandTable(
            self._root, self._tree + ("commandtable",), self._ct_schema_url
        )
