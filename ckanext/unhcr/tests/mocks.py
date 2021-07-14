import cgi
from io import BytesIO


class FakeFileStorage(cgi.FieldStorage, object):

    def __init__(self, fp=None, filename='test.txt'):
        super(FakeFileStorage, self).__init__()
        self.file = fp
        if not fp:
            self.file = BytesIO()
            self.file.write(b'Some data')

        self.list = [self.file]
        self.filename = filename
        self.name = "upload"
