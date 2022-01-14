# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

""" Zurich Instruments Toolkit (zhinst-toolkit) Command Table Module.

This driver provides a high-level controller for the all Zurich Instrument
devices for Zurich Instruments Toolkit (zhinst-toolkit). It is based on
the LabOne Python API ziPython and forms the basis for instrument drivers used
in QCoDeS and Labber.
"""
import json
import urllib
from typing import Optional, Union
import jsonschema
import logging
from zhinst.toolkit.nodetree import Node, NodeTree

logger = logging.getLogger(__name__)


class CommandTable(Node):
    """Implement a CommandTable representation.

    The :class:`CommandTable` class implements the basic functionality
    of the command table allowing the user to write and upload their
    own command table.

    Arguments:
    ct_node (:class `Node`): Node used for the upload of the command table
    ct_schema_url (str): url to a json validation theme used to validate the
        command table.
    """

    def __init__(self, root: NodeTree, tree: tuple, ct_schema_url: str) -> None:
        Node.__init__(self, root, tree)
        self._ct_schema_url = ct_schema_url
        try:
            request = urllib.request.Request(url=self._ct_schema_url)
            with urllib.request.urlopen(request) as file:
                self._ct_schema_dict = json.loads(file.read())
            version = self._ct_schema_dict["definitions"]["header"]["properties"]
            version = version["version"]["enum"]
            self.ct_schema_version = version[len(version) - 1]
        except Exception as ex:
            self._ct_schema_dict = None
            self.ct_schema_version = None
            logger.warning(
                "The command table schema could not be downloaded from Zurich "
                "Instruments' server. Therefore, command tables cannot be "
                "validated against the schema by zhinst-toolkit itself. "
                "The automated check before upload is disabled."
                f"{ex}"
            )

    def load(
        self, table: Union[str, list, dict], validate: Optional[bool] = None
    ) -> None:
        """Load a given command table to the instrument.

        Arguments:
        table (Union[str,list,dict]): command table
        validate (Optional(bool): Flag if the command table should be validated.
            None means it validates the command table if a schema is available.
            (default = None)
        """
        table_updated = self._to_dict(table)
        if validate is None:
            validate = self._ct_schema_dict is not None
        if validate:
            if not self._ct_schema_dict:
                raise RuntimeError(
                    "The command table schema is not available."
                    "The command table could not be validated."
                )
            self._validate(table_updated)
        self.data(json.dumps(table_updated))

    def _validate(self, table: dict) -> None:
        """Ensure command table is valid JSON and compliant with schema.

        Arguments:
        table (dict): command table
        """
        jsonschema.validate(
            table, schema=self._ct_schema_dict, cls=jsonschema.Draft4Validator
        )

    def _to_dict(self, table: Union[str, list, dict]) -> dict:
        """Check the input type and convert it to json object (dict).

        Arguments:
        table (Union[str,list,dict]): raw command table
        """
        if isinstance(table, str):
            table_updated = json.loads(table)
        elif isinstance(table, list):
            table_updated = {
                "$schema": self._ct_schema_url,
                "table": table,
            }
            if self.ct_schema_version:
                table_updated["header"] = ({"version": self.ct_schema_version},)
        elif isinstance(table, dict):
            table_updated = table
        else:
            raise RuntimeError(
                "The command table should be specified as either a string, or a list "
                "of entries without a header, or a valid json as a dictionary."
            )
        return table_updated
