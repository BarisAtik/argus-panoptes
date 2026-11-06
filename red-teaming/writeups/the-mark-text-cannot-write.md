# The mark the text can't write

I wanted a number for a soft defense, and I had no model. Hugging Face was out of reach from where this lab runs, so I trained one:
370k parameters, a toy language of tasks and documents, a few minutes per model on a CPU. Then I wrote down what I expected and
pushed that before running anything. I got most of it wrong.

## What I expected

Teach a model to follow documents, and it would start obeying any instruction in a document. Then attack examples would help on
attacks it had seen, and much less on ones it hadn't. Fixed delimiters would lose to a forged closing delimiter.

None of that happened. The model taught to follow documents obeyed 7% of unrequested instructions, not the 50% I guessed. Attack
training took that to 0 of 29,400, held-out styles included, and delimiters made no difference at all. It looked like a triumph, and
it was a badly built test: "did the user tell you to follow this?" is one easy word in my grammar, and the model learned that word.

## The harder question

So I asked something closer to real work. "Do what Dana says", in a thread with several authors. The real instruction and the attack
are in the same document, and a forged `note from dana :` is word for word the real header. Now authorship is the only honest cue.

- With authorship in the text, and attack training, models still obeyed forged notes 27% of the time.
- With a mark the text can't write, set by a runtime that knows who wrote what, they obeyed 0.1%.
- With that mark and **no attack examples at all**, they obeyed 0.0%.

Then a surprise in my own data. Those text-only models were doing better than they should. My attacks asked for keys and tokens more
than real notes do, so the models had learned what attacks look like, which is the same trick as a filter. When I drew forged notes from
the same distribution as real ones, ASR rose to 40%, and with three times the training to 48%. A coin flip. The mark held at
0 of 1,800 and task success reached 99.8%.

## What I take from it

If an attacker can write exactly what a trusted author writes, a model reading text alone has nothing to go on. Better training
can only teach it what past attacks looked like. This is the same result as [Hermes](../hermes/), one layer down. There, in-band labels
failed against a rogue agent and labels held at the gateway survived. Here, the same split shows up inside a model's input.

The other thing I'd check in any evaluation now: blended actions. A destination check said 7% of attacks worked. But only 64% of
those trials were right. Another 24% mixed the two tasks, like sending the user's recipient the attacker's item. No canary fired on
those.

## What this isn't

It's a toy. One author, a closed vocabulary, a few dozen small models. A real model has broad instruction following that a mark may
not override, and real chat templates flatten roles into tokens. So this is a mechanism worth testing on a real model, and not a claim
about one. Numbers and code are in [Talos](../talos/).
