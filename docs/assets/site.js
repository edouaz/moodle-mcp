const copy = document.querySelector('#copy');
if (copy) copy.addEventListener('click', async () => {
  const french = document.documentElement.lang === 'fr';
  const command = 'git clone https://github.com/edouaz/moodle-mcp.git\ncd moodle-mcp\nbash setup.sh' + (french ? ' --lang fr' : '');
  const status = document.querySelector('#copy-status');
  try {
    await navigator.clipboard.writeText(command);
    copy.textContent = french ? 'Copié ✓' : 'Copied ✓';
    status.textContent = french ? 'Commandes copiées. À vous de jouer !' : 'Commands copied. Your turn!';
    setTimeout(() => { copy.textContent = french ? 'Copier' : 'Copy'; }, 2500);
  } catch {
    status.textContent = french ? 'Sélectionnez les commandes pour les copier.' : 'Select the commands to copy them.';
  }
});
