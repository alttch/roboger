__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"


class FunctionCollecton:

    def __init__(self, on_error=None):
        self.functions = set()
        self.on_error = on_error

    def __call__(self, f):
        self.append(f)

    def append(self, f):
        self.functions.add(f)

    def remove(self, f):
        try:
            self.functions.remove(f)
        except:
            log_traceback()

    def run(self):
        for f in self.functions:
            try:
                f()
            except:
                if self.on_error:
                    self.on_error()
