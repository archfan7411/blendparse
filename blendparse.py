# A purpose-built class to parse certain information from .blend files.

import json
import io
import re

class BlendStruct:
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
    def __init__(self, filename):
        super().__init__(filename, "rb")
        # Offset of first file block header.
        self._block_start = 12
        self.read_header()
        # Offsets of each file block by code.
        self._block_offsets = self._read_block_offsets()
        # SDNA structures by name.
        self._sdna = self._load_sdna()

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

    def _read_block_offsets(self):
        """
        Cache the offset to each file block.
        """

        block_offsets = {}
        self.seek(self._block_start)
        while True:
            offset = self.tell()
            # File block code; identifies type of data
            block_code = self.read(4).decode("utf-8")
            # Empty string indicates EOF.
            if block_code == "":
                break
            block_offsets[block_code] = offset
            # Size of file block, after this header
            block_size = int.from_bytes(self.read(4), self.endianness)

            # Skip rest of file header.
            self.seek(self.pointer_size + 8, io.SEEK_CUR)
            # Skip to next file block.
            self.seek(block_size, io.SEEK_CUR)

        return block_offsets

    def _load_sdna(self):
        """
        Load each SDNA structure.
        """
        try:
            offset = self._block_offsets["DNA1"]
        except KeyError:
            raise ValueError("Missing DNA1 file block.")

        sdna = {}
        # Skip file block header.
        self.seek(offset)
        # File block code.
        self.seek(4, io.SEEK_CUR)
        # Size of file block after this header.
        block_size = int.from_bytes(self.read(4), self.endianness)
        self.seek(8 + self.pointer_size, io.SEEK_CUR)
        block_end = offset + block_size

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

    def read_header(self):
        self.seek(0)

        # File identifier, 8-byte string; should always be "BLENDER"
        self.identifier = self.read(7).decode("utf-8")

        # Pointer size, 1-byte char; '-' indicates 8 bytes, '_' indicates 4
        self.pointer_size = 8 if self.read(1).decode("utf-8") == "-" else 4

        # Endianness, 1-byte char; 'v' indicates little endian, 'V' indicates big
        self.endianness = "little" if self.read(1).decode("utf-8") == "v" else "big"

        # Blender version, 3-byte int; v2.93 is represented as 293, and so on
        self.version = int(self.read(3))

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
        def create_loader(at_offset):
            def load_block():
                return self._load_block(at_offset)
            return load_block

        matched_blocks = {}
        for identifier, offset in self._block_offsets.items():
            if identifier.startswith(match):
                matched_blocks[identifier] = create_loader(offset)
        return matched_blocks

    # Helper for creating a callback to load a given structure.
    def _struct_loader(self, name, at_offset):
        def load_struct():
            return self._load_struct(name, at_offset)
        return load_struct

    def _load_block(self, offset):
        """
        Load a file block at a given offset to the beginning of the blend file.

        :param offset: The offset of the file block.
        :return Generator that yields dictionaries, each representing a struct.
        """
        # We might allow loading cached blocks after the file is closed, so
        # I'm leaving this here to be explicit. XD
        if self.closed:
            raise ValueError("I/O operation on a closed file.")

        # Grab SDNA index and struct count from file block header.
        self.seek(offset + 4 + 4 + self.pointer_size)
        sdna_index = int.from_bytes(self.read(4), self.endianness)
        count = int.from_bytes(self.read(4), self.endianness)

        # The type of the structure.
        name = list(self._sdna["structs"])[sdna_index]
        for _ in range(count):
            yield BlendStruct(self._struct_loader(name, self.tell()), name)