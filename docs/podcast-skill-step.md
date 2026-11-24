# Mount Rushmore skill: save the transcript for the Hub recap

Add this as **step 1b** of the skill, right after the transcript has been read (step 1) and before the segment is worked out.

---

## 1b. Save the transcript for the Hub's weekly recap

Every episode, once the transcript is read, write it to the Hub repo so the weekly recap can use it (the recap finds the Content Boy Coin and the hot takes in it).

1. Build this JSON from the lines you read (nothing else, no edits to the wording):

   ```json
   {"videoId": "<the v= value>", "episode": <number>, "title": "<video title>", "savedAt": "<UTC ISO time>",
    "cues": [{"start": <seconds from the start, a number>, "text": "<the caption line, duration words removed>"}, ...]}
   ```

   `start` is the timestamp shown in the transcript panel turned into seconds (1:02:03 = 3723).

2. Write it with the GitHub connector: repository `namkurd/namkurd.github.io`, branch `main`, path `data/podcast_transcript.json`.
   - If the file exists, read it first (`get_file_contents`) and pass its `sha` to `create_or_update_file`, so it is replaced.
   - Commit message: `Podcast transcript for episode <number>`.
3. Tell Ben it was saved. If the write fails, say so and carry on with the rest of the skill; it never blocks the vote post.

The Hub reads the file, asks a model for the coin winner and hot takes, and keeps only quotes whose exact words are in the transcript.
