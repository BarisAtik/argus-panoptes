"""The 80 COCO object categories with hand-written Dutch noun phrases.

Hand-written so that the experiment measures the model, not a translation model.
Keys are the official COCO category names.
"""

COCO_LABELS: dict[str, tuple[str, str]] = {
    "person": ("a person", "een persoon"), "bicycle": ("a bicycle", "een fiets"),
    "car": ("a car", "een auto"), "motorcycle": ("a motorcycle", "een motor"),
    "airplane": ("an airplane", "een vliegtuig"), "bus": ("a bus", "een bus"),
    "train": ("a train", "een trein"), "truck": ("a truck", "een vrachtwagen"),
    "boat": ("a boat", "een boot"), "traffic light": ("a traffic light", "een stoplicht"),
    "fire hydrant": ("a fire hydrant", "een brandkraan"),
    "stop sign": ("a stop sign", "een stopbord"),
    "parking meter": ("a parking meter", "een parkeermeter"),
    "bench": ("a bench", "een parkbankje"), "bird": ("a bird", "een vogel"),
    "cat": ("a cat", "een kat"), "dog": ("a dog", "een hond"), "horse": ("a horse", "een paard"),
    "sheep": ("a sheep", "een schaap"), "cow": ("a cow", "een koe"),
    "elephant": ("an elephant", "een olifant"), "bear": ("a bear", "een beer"),
    "zebra": ("a zebra", "een zebra"), "giraffe": ("a giraffe", "een giraf"),
    "backpack": ("a backpack", "een rugzak"), "umbrella": ("an umbrella", "een paraplu"),
    "handbag": ("a handbag", "een handtas"), "tie": ("a tie", "een stropdas"),
    "suitcase": ("a suitcase", "een koffer"), "frisbee": ("a frisbee", "een frisbee"),
    "skis": ("a pair of skis", "een paar ski's"), "snowboard": ("a snowboard", "een snowboard"),
    "sports ball": ("a sports ball", "een sportbal"), "kite": ("a kite", "een vlieger"),
    "baseball bat": ("a baseball bat", "een honkbalknuppel"),
    "baseball glove": ("a baseball glove", "een honkbalhandschoen"),
    "skateboard": ("a skateboard", "een skateboard"), "surfboard": ("a surfboard", "een surfplank"),
    "tennis racket": ("a tennis racket", "een tennisracket"), "bottle": ("a bottle", "een fles"),
    "wine glass": ("a wine glass", "een wijnglas"), "cup": ("a cup", "een kopje"),
    "fork": ("a fork", "een vork"), "knife": ("a knife", "een mes"),
    "spoon": ("a spoon", "een lepel"),
    "bowl": ("a bowl", "een kom"), "banana": ("a banana", "een banaan"),
    "apple": ("an apple", "een appel"), "sandwich": ("a sandwich", "een boterham"),
    "orange": ("an orange", "een sinaasappel"), "broccoli": ("broccoli", "broccoli"),
    "carrot": ("a carrot", "een wortel"), "hot dog": ("a hot dog", "een hotdog"),
    "pizza": ("a pizza", "een pizza"), "donut": ("a donut", "een donut"),
    "cake": ("a cake", "een taart"), "chair": ("a chair", "een stoel"),
    "couch": ("a couch", "een bank"), "potted plant": ("a potted plant", "een kamerplant"),
    "bed": ("a bed", "een bed"), "dining table": ("a dining table", "een eettafel"),
    "toilet": ("a toilet", "een wc"), "tv": ("a television", "een televisie"),
    "laptop": ("a laptop", "een laptop"), "mouse": ("a computer mouse", "een computermuis"),
    "remote": ("a remote control", "een afstandsbediening"),
    "keyboard": ("a keyboard", "een toetsenbord"),
    "cell phone": ("a cell phone", "een mobiele telefoon"),
    "microwave": ("a microwave", "een magnetron"), "oven": ("an oven", "een oven"),
    "toaster": ("a toaster", "een broodrooster"), "sink": ("a sink", "een gootsteen"),
    "refrigerator": ("a refrigerator", "een koelkast"), "book": ("a book", "een boek"),
    "clock": ("a clock", "een klok"), "vase": ("a vase", "een vaas"),
    "scissors": ("scissors", "een schaar"), "teddy bear": ("a teddy bear", "een teddybeer"),
    "hair drier": ("a hair drier", "een föhn"), "toothbrush": ("a toothbrush", "een tandenborstel"),
}

# Dutch words that are also English words with another meaning: the worst case for a model that
# only learned English. The bare word is the query; the COCO category is the Dutch meaning.
FALSE_FRIENDS: dict[str, str] = {
    "bank": "couch", "boot": "boat", "beer": "bear", "motor": "motorcycle",
}

TEMPLATES = {"en": "a photo of {}", "nl": "een foto van {}"}
