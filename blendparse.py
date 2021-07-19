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
        
        # Looping through file block headers to find scene header
        for block_code, offset in self._block_offsets.items():
            if block_code.startswith("SC"):
                print(f"Found scene block at offset {offset}!")

    def _read_block_offsets(self):
        """
        Cache the offset to each file block.
        """

        block_offsets = {}
        self.seek(self._block_start)
        while True:
            # File block code; identifies type of data
            block_code = self.read(4).decode("utf-8")
            # Empty string indicates EOF.
            if block_code == "":
                break
            block_offsets[block_code] = self.tell()
            # Size of file block, after this header
            block_size = int.from_bytes(self.read(4), self.endianness)
            
            # Skip rest of file header.
            self.seek(self.pointer_size + 8, io.SEEK_CUR)
            # Skip to next file block.
            self.seek(block_size, io.SEEK_CUR)

        return block_offsets

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