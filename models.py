import persistent

class Person(persistent.Persistent):
    def __init__(self, name, age):
        self.name = name
        self.age = age
