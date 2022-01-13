"""Module for managing a session to a Data Server through zhinst.ziPython."""
from functools import lru_cache
from enum import IntFlag
from typing import Any, Union, Type, List, Tuple
from pathlib import Path
import json
from collections.abc import MutableMapping
import zhinst.ziPython as ziPython
from zhinst.toolkit.nodetree import NodeTree, Node
from zhinst.toolkit.driver.base import BaseInstrument
from zhinst.toolkit.helper import lazy_property


class Devices(MutableMapping):
    """Mapping class for the connected devices.

    Mapps the connected devices from data server to lazy device objects.
    On every access the connected devices are read from the data server. This
    ensures that even if devices get connected/disconnected through another
    session the list will be up to date.

    Args:
        session (DataServerSession): active session to the data server.
    """

    def __init__(self, session: "DataServerSession"):
        self._session = session
        self._devices = {}
        self._device_classes = {}

    def connected(self) -> List[str]:
        """Get a list of devices connected to the data server.

        Returns:
            list[str]: List of all connected devices.
        """
        try:
            return (
                self._session.daq_server.getString("/zi/devices/connected")
                .lower()
                .split(",")
            )
        except RuntimeError:
            return [key for key in self._devices.keys()]

    def visible(self) -> List[str]:
        """Get a list of devices visible to the data server.

        Returns:
            list[str]: List of all connected devices.
        """
        try:
            return (
                self._session.daq_server.getString("/zi/devices/visible")
                .lower()
                .split(",")
            )
        except RuntimeError:
            return ziPython.ziDiscovery().findAll()

    def connect_hf2_device(self, serial):
        if serial in self._devices:
            raise RuntimeError(f"Can only create one instance of {serial}.")
        if not self._session.is_hf2_server:
            raise RuntimeError(
                f"This function can only be used with an HF2 data server"
            )
        self._devices[serial] = self._create_device(serial)

    def __getitem__(self, key):
        if key in self.connected():
            if key not in self._devices:
                self._devices[key] = self._create_device(key)
            return self._devices[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        raise LookupError(
            "Illegal operation. Devices must be connected through the session."
        )

    def __delitem__(self, key):
        self._devices.pop(key, None)

    def __iter__(self):
        return iter(self.connected())

    def __len__(self):
        return len(self.connected())

    def _create_device(self, serial: str) -> Type[BaseInstrument]:
        """Creates a new device object.

        Maps the device type to the correct instrument class (The default is
        the ``BaseInstrument`` which is a generic instrument class that supports
        all devices).
        WARNING: The device must already be connected to the data server

        Args:
            serial (str): device serial

        Returns:
            Type[BaseInstrument] newly created instrument object

        Raises:
            RuntimeError: If the device is not connected to the data server
        """
        try:
            dev_type = self._session.daq_server.getString(f"/{serial}/features/devtype")
            device = self._device_classes.get(dev_type, BaseInstrument)(
                serial, dev_type, self._session
            )
        except RuntimeError as error:
            if (
                self._session.is_hf2_server
                and "ZIAPINotFoundException" in error.args[0]
            ):
                discovery = ziPython.ziDiscovery()
                discovery.find(serial)
                dev_type = discovery.get(serial)["devicetype"]
                raise RuntimeError(
                    "Can only connect HF2 devices to an HF2 data "
                    f"server. {serial} identifies itself as a {dev_type}."
                )
            raise
        return device


class PollFlags(IntFlag):
    """Flags used for polling.

    Can be combinded with bitwise operations
    >>> PollFlags.FILL | PollFlags.DETECT
        <PollFlags.DETECT|FILL: 9>
    """

    DETECT_AND_THROW = 12  # Detect data loss holes and throw EOFError exception
    DETECT = 8  # Detect data loss holes
    FILL = 1  # Fill holes
    DEFAULT = 0  # No Flags


class DataServerSession(Node):
    """Session to a data server.

    TODO go into detail

    Args:
        connection (Union[zi.ziDAQServer, tuple[str, int]]): Either an existing
            daq_server(session to the data server) object or host and port of
            the target data server. default ("localhost", 8004)
        hf2_server (bool): Flag if the data server is a hf2_server.
            Changes the default port to 8005. (default = False)
    """

    def __init__(
        self,
        connection: Union[ziPython.ziDAQServer, Tuple[str, int]] = ("localhost", 8004),
        hf2: bool = None,
    ):
        self._is_hf2_server = hf2 if hf2 is not None else False
        self._cache = {}
        if isinstance(connection, type(ziPython.ziDAQServer)):
            if hf2 is not None:
                if self._is_hf2_server and "HF2" not in connection.getString(
                    "/zi/about/dataserver"
                ):
                    raise RuntimeError(
                        "hf2_server Flag was set but the passed "
                        "DAQServer instance is no HF2 data server."
                    )
                elif not hf2 and "HF2" in connection.getString("/zi/about/dataserver"):
                    raise RuntimeError(
                        "hf2_server Flag was reset but the passed "
                        "DAQServer instance is a HF2 data server."
                    )
            else:
                if "HF2" in connection.getString("/zi/about/dataserver"):
                    self._is_hf2_server = True
                else:
                    self._is_hf2_server = False
            self._server_host = None
            self._server_port = None
            self._daq_server = connection
        else:
            self._server_host = connection[0]
            self._server_port = connection[1]
            if self._is_hf2_server and self._server_port == 8004:
                self._server_port = 8005
            try:
                self._daq_server = ziPython.ziDAQServer(
                    self._server_host,
                    self._server_port,
                    1 if self._is_hf2_server else 6,
                )
            except RuntimeError as e:
                if "Unsupported API level" in e.args[0]:
                    if hf2 is None:
                        self._is_hf2_server = True
                        self._daq_server = ziPython.ziDAQServer(
                            self._server_host,
                            self._server_port,
                            1,
                        )
                    elif not hf2:
                        raise RuntimeError(
                            "hf2_server Flag was reset but the specified "
                            f"server at {self._server_host}:{self._server_port} is a "
                            "HF2 data server."
                        )
                else:
                    raise
        if self._is_hf2_server and "HF2" not in self._daq_server.getString(
            "/zi/about/dataserver"
        ):
            raise RuntimeError(
                "hf2_server Flag was set but the specified "
                f"server at {self._server_host}:{self._server_port} is not a "
                "HF2 data server."
            )
        self._devices = Devices(self)

        hf2_node_doc = Path(__file__).parent / "nodedoc_hf2_data_server.json"
        nodetree = NodeTree(
            self.daq_server,
            prefix_hide="zi",
            list_nodes=["/zi/*"],
            preloaded_json=json.loads(hf2_node_doc.open("r").read())
            if self._is_hf2_server
            else None,
        )
        super().__init__(nodetree, tuple())

    def __repr__(self):
        return str(
            f"{'HF2' if self._is_hf2_server else ''}DataServerSession("
            f"{self._server_host}:{self._server_port})"
        )

    def connect_device(
        self, serial: str, interface: str = None
    ) -> Type[BaseInstrument]:
        """Establish a connection to a device.

        Args:
            serial (str): Serial number of the device, e.g. *'dev12000'*.
                The serial number can be found on the back panel of the instrument.
            interface (str): Device interface (e.g. = "1GbE"). If not specified
                the default interface from the discover is used.

        Returns:
            Type[BaseInstrument]: Device object
        """
        serial = serial.lower()
        if serial not in self._devices:
            if not interface:
                if self._is_hf2_server:
                    interface = "USB"
                else:
                    # Take interface from the discovery
                    interface = json.loads(self.daq_server.getString("/zi/devices"))[
                        serial.upper()
                    ]["INTERFACE"]
            self._daq_server.connectDevice(serial, interface)
            if self._is_hf2_server:
                self._devices.connect_hf2_device(serial)
        return self._devices[serial]

    def disconnect_device(self, serial: str) -> None:
        """Disconnect a device.

        This function will return immediately. The disconnection of the device
        may not yet finished.

        Args:
            serial (str): Serial number of the device, e.g. *'dev12000'*.
                The serial number can be found on the back panel of the instrument.
        """
        self._devices.pop(serial, None)
        self.daq_server.disconnectDevice(serial)

    @property
    def devices(self) -> Devices:
        """Mapping for the connected devices."""
        return self._devices

    @property
    def is_hf2_server(self) -> bool:
        """Flag if the data server is a HF2 Data Server"""
        return self._is_hf2_server

    @property
    def daq_server(self) -> ziPython.ziDAQServer:
        """Managed instance of the ziPython.ziDAQServer."""
        return self._daq_server

    def sync(self) -> None:
        """Synchronize all connected devices.

        Synchronization in this case means creating a defined state.
        The following steps are performed:
            * Ensures that all set commands have been flushed to the device
            * Ensures that get and poll commands only return data which was
              recorded after the sync command. (ALL poll buffers are cleared!)
            * Blocks until all devices have cleared their bussy flag.

        WARNING: The sync is performed for all devices connected to the daq server
        WARNING: This command is a blocking command that can take a substential
                 amount of time.

        Raises:
            RuntimeError: ZIAPIServerException: Timeout during sync of device
        """
        self.daq_server.sync()

    def poll(
        self,
        recording_time: float = 0.1,
        timeout: float = 0.5,
        flags: PollFlags = PollFlags.DEFAULT,
        flat: bool = True,
    ) -> dict:
        """Polls all subsribed data

        Poll the value changes in all subscribed nodes since either subscribing
        or the last poll (assuming no buffer overflow has occurred on the Data Server).

        Args:
            recording_time (float): defines the duration of the poll. (Note that
                not only the newly recorder values are polled but all vaules
                since either subscribing or the last pill). Needs to be larger
                than zero. (default = 0.1)
            timeout (float): Adds an additional timeout in seconds on top of
                ``recording_time``. Only relevant when communicating in a slow
                network. In this case it may be set to a value larger than the
                expected round-trip time in the network. (default = 0.5)
            flags (PollFlags): Flags for the polling (see :class ``PollFlags??:)
            flat (bool): If False the returned dictionary is a nested dictionary

        Returns:
            dict: Polled data in a dictionary.
        """
        data_raw = self.daq_server.poll(
            recording_time, int(timeout * 1000), flags=flags.value, flat=flat
        )
        polled_data = {}
        if data_raw:
            for node, data in data_raw.items():
                node_split = node.split("/")
                device = self.devices[node_split[1]]

                node = Node(device.nodetree, tuple(node_split[2:]))
                if device not in data:
                    polled_data[device] = {}
                polled_data[device][node] = data
        return polled_data

    #################################
    #### ziPython module mapping ####
    #################################

    @staticmethod
    def _add_nodetree(module: Any) -> None:
        """Add a nodtree property to to existing module

        The nodetree property offer the option to acces nodes in a pythonic way.

        The property is added to the class and is implemented with an lru cache
        which pervents multiple instantiations of the nodetree.

        Args:
            module (Any): object to which class the nodetree should be added.
                (needs to have the Protocol specfied in class:`Connection`)
        """

        @lru_cache()
        def nodetree(self):
            """High-level node tree

            Helps to access the nodes of the module in a pythonic way.
            """
            return NodeTree(self)

        module.__class__.nodetree = property(nodetree, None, None, "nodetree")

    def create_awg_module(self) -> ziPython.AwgModule:
        """Create an instance of the AwgModule.

        In contrast to ziPython.ziDAQServer.awgModule() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `awg_module`.

        Returns:
            ziPython.AwgModule: created module
        """
        module = self.daq_server.awgModule()
        self._add_nodetree(module)
        return module

    def create_daq_module(self) -> ziPython.DataAcquisitionModule:
        """Create an instance of the AwgModule.

        In contrast to ziPython.ziDAQServer.awgModule() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `awg_module`.

        Returns:
            ziPython.AwgModule: created module
        """
        module = self.daq_server.dataAcquisitionModule()
        self._add_nodetree(module)
        return module

    def create_device_settings_module(self) -> ziPython.DeviceSettingsModule:
        """Create an instance of the DeviceSettingsModule.

        In contrast to ziPython.ziDAQServer.deviceSettings() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `device_settings_module`.

        Returns:
            ziPython.DeviceSettingsModule created module
        """
        module = self.daq_server.deviceSettings()
        self._add_nodetree(module)
        return module

    def create_impedance_module(self) -> ziPython.ImpedanceModule:
        """Create an instance of the ImpedanceModule.

        In contrast to ziPython.ziDAQServer.impedanceModule() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `impedance_module`.

        Returns:
            ziPython.ImpedanceModule: created module
        """
        module = self.daq_server.impedanceModule()
        self._add_nodetree(module)
        return module

    def create_mds_module(self) -> ziPython.MultiDeviceSyncModule:
        """Create an instance of the MultiDeviceSyncModule.

        In contrast to ziPython.ziDAQServer.multiDeviceSyncModule() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `mds_module`.

        Returns:
            ziPython.MultiDeviceSyncModule: created module
        """
        module = self.daq_server.multiDeviceSyncModule()
        self._add_nodetree(module)
        return module

    def create_pid_advisor_module(self) -> ziPython.PidAdvisorModule:
        """Create an instance of the PidAdvisorModule.

        In contrast to ziPython.ziDAQServer.pidAdvisor() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `pid_advisor_module`.

        Returns:
            ziPython.PidAdvisorModule: created module
        """
        module = self.daq_server.pidAdvisor()
        self._add_nodetree(module)
        return module

    def create_precompensation_advisor_module(
        self,
    ) -> ziPython.PrecompensationAdvisorModule:
        """Create an instance of the PrecompensationAdvisorModule.

        In contrast to ziPython.ziDAQServer.precompensationAdvisor() a nodetree property
        is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `precompensation_advisor_module`.

        Returns:
            ziPython.PrecompensationAdvisorModule: created module
        """
        module = self.daq_server.precompensationAdvisor()
        self._add_nodetree(module)
        return module

    def create_qa_module(self) -> ziPython.QuantumAnalyzerModule:
        """Create an instance of the QuantumAnalyzerModule.

        In contrast to ziPython.ziDAQServer.quantumAnalyzerModule() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `qa_module`.

        Returns:
            ziPython.QuantumAnalyzerModule created module
        """
        module = self.daq_server.quantumAnalyzerModule()
        self._add_nodetree(module)
        return module

    def create_recorder_module(self) -> ziPython.RecorderModule:
        """Create an instance of the RecorderModule.

        In contrast to ziPython.ziDAQServer.record() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `recorder_module`.

        Returns:
            ziPython.RecorderModule created module
        """
        module = self.daq_server.record()
        self._add_nodetree(module)
        return module

    def create_scope_module(self) -> ziPython.ScopeModule:
        """Create an instance of the ScopeModule.

        In contrast to ziPython.ziDAQServer.awgModule() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `awg_module`.

        Returns:
            ziPython.AwgModule created module
        """
        module = self.daq_server.scopeModule()
        self._add_nodetree(module)
        return module

    def create_sweeper_module(self) -> ziPython.SweeperModule:
        """Create an instance of the SweeperModule.

        In contrast to ziPython.ziDAQServer.sweep() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `sweeper_module`.

        Returns:
            ziPython.ScopeModule created module
        """
        module = self.daq_server.sweep()
        self._add_nodetree(module)
        return module

    def create_zoom_fft_module(self) -> ziPython.ZoomFFTModule:
        """Create an instance of the ZoomFFTModule.

        In contrast to ziPython.ziDAQServer.zoomFFT() a nodetree property is added.

        The new instance creates a new session to the DataServer.
        New instances should therefor be created carefully since they consume
        resources.

        The new module is not managed by toolkit. A managed instance is provided
        by the property `zoom_fft`.

        Returns:
            ziPython.ZoomFFTModule created module
        """
        module = self.daq_server.zoomFFT()
        self._add_nodetree(module)
        return module

    @lazy_property
    def awg_module(self) -> ziPython.AwgModule:
        """Managed instance of the ziPython.AwgModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_awg_module()

    @lazy_property
    def daq_module(self) -> ziPython.DataAcquisitionModule:
        """Managed instance of the ziPython.DataAcquisitionModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_daq_module()

    @lazy_property
    def device_settings_module(self) -> ziPython.DeviceSettingsModule:
        """Managed instance of the ziPython.DeviceSettingsModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_device_settings_module()

    @lazy_property
    def impedance_module(self) -> ziPython.ImpedanceModule:
        """Managed instance of the ziPython.ImpedanceModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_impedance_module()

    @lazy_property
    def mds_module(self) -> ziPython.MultiDeviceSyncModule:
        """Managed instance of the ziPython.MultiDeviceSyncModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_mds_module()

    @lazy_property
    def pid_advisor_module(self) -> ziPython.PidAdvisorModule:
        """Managed instance of the ziPython.PidAdvisorModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_pid_advisor_module()

    @lazy_property
    def precompensation_advisor_module(self) -> ziPython.PrecompensationAdvisorModule:
        """Managed instance of the ziPython.PrecompensationAdvisorModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_precompensation_advisor_module()

    @lazy_property
    def qa_module(self) -> ziPython.QuantumAnalyzerModule:
        """Managed instance of the ziPython.QuantumAnalyzerModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_qa_module()

    @lazy_property
    def recorder_module(self) -> ziPython.RecorderModule:
        """Managed instance of the ziPython.RecorderModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_recorder_module()

    @lazy_property
    def scope_module(self) -> ziPython.ScopeModule:
        """Managed instance of the ziPython.ScopeModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_scope_module()

    @lazy_property
    def sweeper_module(self) -> ziPython.SweeperModule:
        """Managed instance of the ziPython.SweeperModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_sweeper_module()

    @lazy_property
    def zoom_fft_module(self) -> ziPython.ZoomFFTModule:
        """Managed instance of the ziPython.ZoomFFTModule.

        Managed in this sense means that only one instance is created
        and hold inside the connection Manager. This makes it easier to access
        the modules from with toolkit, since creating a module requires
        ressources.
        """
        return self.create_zoom_fft_module()
