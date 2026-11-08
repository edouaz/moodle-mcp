const copy = document.querySelector('#copy');
if (copy) copy.addEventListener('click', async () => {
  const command = 'git clone https://github.com/edouaz/moodle-mcp.git\ncd moodle-mcp\nbash setup.sh';
  const status = document.querySelector('#copy-status');
  try {
    await navigator.clipboard.writeText(command);
    copy.textContent = 'Copié ✓';
    status.textContent = 'Commandes copiées. À vous de jouer !';
    setTimeout(() => { copy.textContent = 'Copier'; }, 2500);
  } catch {
    status.textContent = 'Sélectionnez les commandes pour les copier.';
  }
});
