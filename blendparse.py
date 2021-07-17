# A purpose-built class to parse certain information from .blend files.

import io

# A class for opening and reading data from .blend files
class Blendfile():
    def __init__(self, filename):
        self.filename = filename
        with open(filename, "rb") as f:
            self.stream = io.BufferedReader(f)
            self.stream.seek(0)

            # File identifier, 8-byte string; should always be "BLENDER"
            self.identifier = self.stream.read(7).decode("utf-8")

            # Pointer size, 1-byte char; '-' indicates 8 bytes, '_' indicates 4
            self.pointer_size = 8 if self.stream.read(1).decode("utf-8") == "-" else 4

            # Endianness, 1-byte char; 'v' indicates little endian, 'V' indicates big
            self.endianness = "little" if self.stream.read(1).decode("utf-8") == "v" else "big"

            # Blender version, 3-byte int; v2.93 is represented as 293, and so on
            self.version = int(self.stream.read(3))

            # Looping through file block headers to find scene header
            # TODO: Implement proper error handling if the target file block does not exist.
            while True:

                # File block code; identifies type of data
                code = self.stream.read(4).decode("utf-8")

                # Size of file block, after this header
                size = int.from_bytes(self.stream.read(4), self.endianness)

                # Seeking to end of file block header
                self.stream.seek(8+self.pointer_size+size, 1)

                # Scene file block codes will always begin with "SC"
                if code.startswith("SC"):
                    # TODO: Acquire SDNA index of scene data, to be found in DNA1 file block
                    # SDNA index occurs directly following file block size in header
                    # and is pointer_size bytes long
                    break
                
                # Seeking to the start of the next file block
                self.stream.seek(8+self.pointer_size+size, 1)