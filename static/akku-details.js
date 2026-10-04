// Anfangs einklappen der Batterie-Details
const akkuContent = document.getElementById('akkuContent');
akkuContent.style.display = 'none';

// Klick auf Header toggelt nur die Batterie-Details
document.getElementById('akkuHeader').addEventListener('click', () => {
    akkuContent.style.display = (akkuContent.style.display === 'none') ? 'block' : 'none';
});
