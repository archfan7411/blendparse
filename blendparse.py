# A purpose-built class to parse certain information from .blend files.

import io

# A class for opening and reading data from .blend files
class Blendfile(io.FileIO):
    def __init__(self, filename):
        super().__init__(filename, "rb")
        # Offset of first file block header.
        self._block_start = 12
        self.read_header()
        # Offsets of each file block by code.
        self._block_offsets = self._read_block_offsets()

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

    def _read_sdna_indexes(self):
        """
        Cache the index and offset of each SDNA structure name.
        """
        pass

    def _load_sdna(self, sdna_index):
        """
        Load an SDNA struct as a dict describing the structures.
        """
        # We could consider caching recently loaded SDNA structs.
        pass

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

        sdna_struct = self._load_sdna(sdna_index)

        # TODO load structs according to SDNA.
        for _ in range(count):
            translated = {}
            yield translated