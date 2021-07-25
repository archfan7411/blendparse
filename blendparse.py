# A purpose-built class to parse certain information from .blend files.

import collections
import json
import io
import re
import struct

class BlendDecodeError(Exception):
    pass

class BlendStruct(collections.abc.Mapping):
    """
    Read-only dict-like datatype representing a structure in a .blend file.
    """

    def __init__(self, load_cb, type):
        """
        Initialize the BlendStruct.

        :param load_cb: A callback to load the structure.
        :param type: The type of the structure.
        """
        self._load_cb = load_cb
        self._type = type
        self._structure = None

    def load(self):
        """
        Force the structure to be loaded.

        :return The loaded blend struct (self)
        """
        if self._structure is None:
            self._structure = self._load_cb()
        return self

    def __str__(self):
        if self._structure is None:
            return f"<Blender Structure {self._type} (unloaded)>"
        else:
            return str(self._structure)

    def __repr__(self):
        if self._structure is None:
            return f"<Blender Structure {self._type} (unloaded)>"
        else:
            return f"<Blender Structure {self._type} (loaded)>"

    def __getitem__(self, item):
        if self._structure is None:
            self._structure = self._load_cb()
        return self._structure[item]

    def __iter__(self):
        if self._structure is None:
            self._structure = self._load_cb()
        return self._structure.__iter__()

    def __len__(self):
        if self._structure is None:
            self._structure = self._load_cb()
        return len(self._structure)

    def inspect(self):
        """
        Return a human readable representation of the struct.
        """
        summary = {}
        if self._structure is None:
            self._structure = self._load_cb()
        for field, value in self._structure.items():
            summary[field] = repr(value)
        return json.dumps(summary, indent=4)

# A class for opening and reading data from .blend files
class Blendfile(io.FileIO):

    # The .blend format begins with a file header consisting of four fields.
    # A 7 byte identifier string, which will always be "BLENDER"
    # A single char representing pointer size: "-" for 8 byte, "_" for 4 byte.
    # A single char representing endianness: "v" for little, "V" for big.
    # A 3 byte version string. For example "293" indicates version 2.93.
    _blend_header_struct = struct.Struct("7scc3s")
    _BlendHeader = collections.namedtuple(
       "FileHeader", ("identifier", "pointer_size", "endianness", "version"))

    # The file header is followed by a series of file blocks. Each file block
    # begins with a header that contains 5 fields.
    # A 4 byte code string which is the name of the file block.
    # A 4 byte integer representing the size in bytes of the file block body.
    # A pointer_size byte memory address (string); the old location in memory.
    # A 4 byte integer representing the index of the struct definition
    # in the SDNA struct array.
    # A 4 byte integer representing the number of structs in the file block.
    # The struct object depends on the pointer size read during initialization,
    # so it will be initialized per instance at that time.
    # The code is called blockcode to distinguish it from the code module.
    _BlockHeader = collections.namedtuple(
        "BlockHeader", ("blockcode", "size", "address", "sdna_index", "count"))

    def __init__(self, filename):
        super().__init__(filename, "rb")
        # Offset of first file block header.
        self._block_start = 12
        self._load_header()

        # Endianess symbol for struct format string.
        if self.endianness == "big":
            endianness_format = ">"
        else:
            endianness_format = "<"
        self._block_header_struct = struct.Struct(
            f"{endianness_format}4si{self.pointer_size}sii")

        # Offsets of each file block by code.
        self._block_offsets = self._read_block_headers()
        # SDNA structures by name.
        self._sdna = self._load_sdna()

    def __str__(self):
        return f"Blender file version {self.version}"

    def _read_c_string(self):
        """
        Utility method to read a null-terminated C-string.
        """
        res = bytes("", "utf-8")
        null_char = bytes("\0", "utf-8")
        while True:
            char = self.read(1)
            if char == null_char:
                return res.decode("utf-8")
            res += char

    def _construct_value(self, type, is_ptr, length):
        """
        Construct a value from a type.
        
        This is gonna be messy; documentation can come later.
        """
        if length > 1:
            arr = []
            # Skip for now.
            size = self._sdna["tlen"][type]
            for _ in range(length):
                self.seek(size, io.SEEK_CUR)
                #arr.append(self._construct_value(type, False, 1))
            return arr

        INT_TYPES = ("short", "int", "long", "long long")
        if type in self._sdna["structs"]:
            offset = self.tell()
            self.seek(self._sdna["tlen"][type], io.SEEK_CUR)
            return BlendStruct(self._struct_loader(type, offset), type)
        elif type in INT_TYPES:
            size = self._sdna["tlen"][type]
            return int.from_bytes(self.read(size), self.endianness)
        elif type == "char":
            if is_ptr:
                return self._read_c_string()
            else:
                return self.read(1)
        else:
            size = self._sdna["tlen"][type]
            self.seek(size, io.SEEK_CUR)
            return type

    def _load_header(self):
        """
        Unpack the file header.

        Verifies the file identifier, and sets the pointer size, endianess, and
        blender version.

        :raises BlendDecodeError
        """
        self.seek(0)
        header_size = self._blend_header_struct.size
        # Does not decode bytes. Decoding bytes could raise an exception, so
        # by validating the fields ourselves by comparing bytes, we can raise
        # an exception with more useful information.
        header = self._BlendHeader(
            *self._blend_header_struct.unpack_from(self.read(header_size)))

        if header.identifier != bytes("BLENDER", "utf-8"):
            raise BlendDecodeError("File identifier is not 'BLENDER'!")
        if header.pointer_size == bytes("-", "utf-8"):
            self.pointer_size = 8
        elif header.pointer_size == bytes("_", "utf-8"):
            self.pointer_size = 4
        else:
            raise BlendDecodeError(
                f"Invalid pointer size character {header.pointer_size}; " \
                f"must be {b'-'} or {b'_'}!")
        if header.endianness == bytes("v", "utf-8"):
            self.endianness = "little"
        elif header.endianess == bytes("V", "utf-8"):
            self.endianness = "big"
        else:
            raise BlendDecodeError(
                f"Invalid endianness character {header.endianess}; "\
                f"must be {b'v'} or {b'V'}")
        if not header.version.isdigit():
            raise BlendDecodeError(
                f"Invalid version string {header.version}!")
        self.version = "v{}.{}{}".format(*header.version.decode("utf-8"))

    def _read_block_headers(self):
        """
        Read the header of each file block and store the offset of its body.

        :return A dict of file block codes mapped to tuples of the format
        (_BlockHeader, byte_offset).
        """

        block_offsets = {}
        self.seek(self._block_start)
        while True:
            # If no bytes are read we are at EOF.
            header_bytes = self.read(self._block_header_struct.size)
            if len(header_bytes) == 0:
                break

            # Header will be read and then recreated with decoded values.
            header = self._BlockHeader(
                *self._block_header_struct.unpack_from(header_bytes))
            try:
                blockcode = header.blockcode.decode("utf-8")
            except UnicodeDecodeError as e:
                # Workaround to avoid having "During handling of..." error.
                raise BlendDecodeError(
                    f"Can't decode block code {header.blockcode}!") from None
            header_decoded = self._BlockHeader(
                blockcode, header.size, header.address,
                header.sdna_index, header.count)

            # Beginning of file block body.
            offset = self.tell()
            block_offsets[blockcode] = (header_decoded, offset)
            self.seek(header_decoded.size, io.SEEK_CUR)

        return block_offsets

    def _load_sdna(self):
        """
        Load each SDNA structure.
        """
        try:
            offset = self._block_offsets["DNA1"][1]
        except KeyError:
            raise ValueError("Missing DNA1 file block.") from None

        sdna = {}
        # Skip file block header.
        self.seek(offset)

        # Identifier; should be "SDNA"
        self.seek(4, io.SEEK_CUR)
        # Name; should be "NAME"
        self.seek(4, io.SEEK_CUR)

        # List of structure names.
        total_names = int.from_bytes(self.read(4), self.endianness)
        names = []
        for _ in range(total_names):
            names.append(self._read_c_string())
        sdna["names"] = names

        # List of types
        # Align at 4 bytes.
        if self.tell() % 4 != 0:
            self.seek(4 - (self.tell() % 4), io.SEEK_CUR)
        # Type identifier; should be "TYPE"
        type_identifier = self.read(4).decode("utf-8")
        assert(type_identifier == "TYPE")
        # Number of types follows.
        total_types = int.from_bytes(self.read(4), self.endianness)
        # Avoiding collision with builtin types module.
        _types = []
        for _ in range(total_types):
            _types.append(self._read_c_string())
        sdna["types"] = _types

        # Length of each type.
        # Align at 4 bytes.
        if self.tell() % 4 != 0:
            self.seek(4 - (self.tell() % 4), io.SEEK_CUR)
        # Type length identifier; should be "TLEN"
        len_identifier = self.read(4).decode("utf-8")
        assert(len_identifier == "TLEN")
        type_lengths = {}
        for i in range(total_types):
            length = int.from_bytes(self.read(2), self.endianness)
            type_lengths[_types[i]] = length
        sdna["tlen"] = type_lengths

        # Align at 4 bytes.
        if self.tell() % 4 != 0:
            self.seek(4 - (self.tell() % 4), io.SEEK_CUR)
        # Structure identifier; should be "STRC".
        struct_identifier = self.read(4).decode("utf-8")
        assert(struct_identifier == "STRC")
        structs = {}
        # Number of structures follows.
        total_structs = int.from_bytes(self.read(4), self.endianness)
        for _ in range(total_structs):
            # Index in types containing the name of the structure.
            type_index = int.from_bytes(self.read(2), self.endianness)
            fields = {}
            # Number of fields in this structure.
            total_fields = int.from_bytes(self.read(2), self.endianness)
            for _ in range(total_fields):
                # Index in type
                field_type = int.from_bytes(self.read(2), self.endianness)
                # Index in name
                field_name = int.from_bytes(self.read(2), self.endianness)
                fields[names[field_name]] = _types[field_type]
            structs[_types[type_index]] = fields
        sdna["structs"] = structs

        return sdna

    def _load_struct(self, struct_name, offset):
        """
        Load a struct according to the SDNA.

        :param struct_name: The name of the structure type.
        :param offset: The byte offset at which to begin loading.
        :return The loaded structure.
        """
        structure = {}
        fields = self._sdna["structs"][struct_name]
        for name, type in fields.items():
            lengths = re.findall(r"\[([0-9]+)\]", name)
            if len(lengths) > 1:
                raise ValueError(f"Can't handle nested array {name}.")
            elif len(lengths) == 1:
                length = int(lengths[0])
            else:
                length = 1
            is_ptr = name.startswith("*")
            structure[name] = self._construct_value(type, is_ptr, length)
        return structure

    def get_blocks(self, match=""):
        """
        Get file blocks from the blend file.

        To be efficient, functions that load the file blocks will be returned.

        :param match: Filter file blocks by matching the beginning of the name
        against a string. Default is "" (matches everything). Case sensitive.
        :return A dictionary mapping identifiers to a function to load the
        block.
        """
        # Invoking the load_block() closure will load the file block at offset.
        def create_loader(header, at_offset):
            def load_block():
                return self._load_block(header, at_offset)
            return load_block

        matched_blocks = {}
        for identifier, header in self._block_offsets.items():
            if identifier.startswith(match):
                matched_blocks[identifier] = create_loader(*header)
        return matched_blocks

    # Helper for creating a callback to load a given structure.
    def _struct_loader(self, name, at_offset):
        def load_struct():
            return self._load_struct(name, at_offset)
        return load_struct

    def _load_block(self, header, offset):
        """
        Load a file block at a given offset to the beginning of the blend file.

        :param header: The file block header.
        :param offset: The byte offset to the file block body.
        :return Generator that yields dictionaries, each representing a struct.
        """
        # We might allow loading cached blocks after the file is closed, so
        # I'm leaving this here to be explicit. XD
        if self.closed:
            raise ValueError("I/O operation on a closed file.")

        # The type of the structure.
        name = list(self._sdna["structs"])[header.sdna_index]
        for _ in range(header.count):
            yield BlendStruct(self._struct_loader(name, self.tell()), name)

__all__ = ("BlendStruct", "Blendfile")