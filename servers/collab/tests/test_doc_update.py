from pycrdt import Doc, Map, Array, Text
from sessions import log_doc_state

def test_doc_update():
    #m = { 'a': 1 }
    #d = Doc({
        #'scene': Map({
            #'camera': Array([1, 2, 3]),
            #'name': Text("foo"),
            #'properties': Map({"foo": 42})
        #})})
    d0 = Doc()
    d0_state = d0.get_state()
    d0['scene'] = Map({'key': Text("foo")})

    d1 = Doc()
    update = d0.get_update()
    d1['scene'] = Map({'key2': Text("bar")})
    d1.apply_update(update)

    d2 = Doc()
    d2['scene'] = Map()
    d2_state = d2.get_state()
    update = d0.get_update(d2_state)
    d2.apply_update(update)

    log_doc_state(d0)
    log_doc_state(d1)
    log_doc_state(d2)


def test_doc_update_2():
    d = Doc()
    d['scene'] = m = Map()
    m['camera'] = Array([1, 2, 3])
    m['name'] = Text("foo")
    m['properties'] = Map({"foo": 42})

    d2 = Doc()
    state = d.get_update()
    d2.apply_update(state)
    log_doc_state(d)
    # log_doc_state(d2)