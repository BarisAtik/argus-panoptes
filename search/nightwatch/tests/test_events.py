import json
import zipfile

from nightwatch.events import flatten_evtx, normalise_flat, read_zip_events
from nightwatch.sources import read_sample, split_of


def evtx(**data):
    return {
        "Event": {
            "System": {
                "Provider": {"#attributes": {"Name": "Microsoft-Windows-Sysmon"}},
                "EventID": 1,
                "Channel": "Microsoft-Windows-Sysmon/Operational",
                "Computer": "LAB-1",
            },
            "EventData": data,
        }
    }


def test_flatten_gives_strings_and_provider():
    flat = flatten_evtx(evtx(Image="a.exe", ProcessId=44, Note=None))
    assert flat["EventID"] == "1"
    assert flat["ProcessId"] == "44"
    assert flat["Provider_Name"] == "Microsoft-Windows-Sysmon"
    assert "Note" not in flat


def test_eventid_with_qualifiers():
    record = evtx()
    record["Event"]["System"]["EventID"] = {"#attributes": {"Qualifiers": 0}, "#text": 7045}
    assert flatten_evtx(record)["EventID"] == "7045"


def test_userdata_wrapper_is_opened():
    record = evtx()
    del record["Event"]["EventData"]
    record["Event"]["UserData"] = {"LogFileCleared": {"SubjectUserName": "x"}}
    assert flatten_evtx(record)["SubjectUserName"] == "x"


def test_list_values_join():
    assert flatten_evtx(evtx(Data=["a", "b"]))["Data"] == "a\nb"


def test_flat_events_get_provider_and_lose_shipper_fields():
    flat = normalise_flat({"SourceName": "S", "@timestamp": "t", "EventID": 4688})
    assert flat == {"SourceName": "S", "Provider_Name": "S", "EventID": "4688"}


def test_read_zip_skips_bad_lines(tmp_path):
    path = tmp_path / "a.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.json", '{"EventID": 1}\nnot json\n\n[1]\n{"EventID": 2}\n')
        archive.writestr("readme.txt", "ignored")
    assert [e["EventID"] for e in read_zip_events(path)] == ["1", "2"]


def test_read_sample_handles_concatenated_objects(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(evtx(A="1")) + "\n" + json.dumps(evtx(A="2")))
    assert [e["A"] for e in read_sample(path)] == ["1", "2"]
    path.write_text(json.dumps([evtx(A="3")]))
    assert [e["A"] for e in read_sample(path)] == ["3"]


def test_split_is_stable_and_about_one_fifth():
    assert split_of("abc") == split_of("abc")
    share = sum(split_of(str(i)) == "dev" for i in range(5000)) / 5000
    assert 0.17 < share < 0.23
