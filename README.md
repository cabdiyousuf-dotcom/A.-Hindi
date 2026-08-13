# Abdi Yousuf — Personal Website

A static personal biography + journal site. No build step, no Node/npm required —
plain HTML, styled with Tailwind's CDN build and Google Fonts (Playfair Display +
Inter).

## Structure

```
index.html              Home page: hero, about, experience timeline, writing, contact
blog/index.html          Journal listing page
blog/posts/*.html        Individual journal entries
css/style.css             Small custom styles (fonts, timeline line, smooth scroll)
images/                   Put a portrait photo here, e.g. images/portrait.jpg
```

To use a real photo instead of the "AY" placeholder circle, add an image to
`images/` and swap the placeholder `<span>` block in `index.html`'s hero section
for an `<img>` tag (the exact line is commented right above it).

## Preview locally

No install needed — Python's built-in server works:

```bash
cd "Personal Website"
python3 -m http.server 8000
```

Then open http://localhost:8000 in a browser.

## Publish for free with GitHub Pages

1. Create a free GitHub account at github.com if you don't already have one.
2. Create a new repository (e.g. `abdi-yousuf-website`) — public, no README/license
   needed since this folder already has one.
3. From this folder, run:

   ```bash
   git add -A
   git commit -m "Initial site"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

4. On GitHub, go to the repo's **Settings → Pages**, set "Source" to the `main`
   branch, root folder, and save.
5. GitHub will publish the site at
   `https://<your-username>.github.io/<repo-name>/` within a minute or two.

If you'd like a custom domain (e.g. `abdiyousuf.com`) later, that's a separate
step (buying the domain, then pointing its DNS at GitHub Pages) — ask and I can
walk through it once you have one.

## Editing content

Everything is in the HTML files directly — no CMS or database. To add a new
journal entry:

1. Copy `blog/posts/welcome.html` to a new file, e.g. `blog/posts/my-new-post.html`.
2. Edit the title and body text.
3. Add a link/card for it in `blog/index.html`, matching the existing pattern.

The bio text in `index.html`'s About section is marked as a draft — review it
carefully (dates, titles, employer names) before treating it as final.
