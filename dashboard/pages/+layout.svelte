<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;700&display=swap" rel="stylesheet" />
</svelte:head>

<slot />

<style>
  :global(body),
  :global(p),
  :global(td),
  :global(th),
  :global(span),
  :global(li),
  :global(a),
  :global(input),
  :global(select) {
    font-family: 'Montserrat', sans-serif;
    font-weight: 300;
  }

  :global(h1),
  :global(h2),
  :global(h3),
  :global(h4),
  :global(h5),
  :global(h6) {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700;
  }
</style>
