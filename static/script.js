document.addEventListener('DOMContentLoaded', function() {
  const startBtn = document.getElementById('start-btn');
  
  // Fetch initial stats
  fetchStats();

  // Set up periodic stats update
  setInterval(fetchStats, 1000); // Update every minute

  startBtn.addEventListener('click', function() {
      if (startBtn.textContent === 'Camera Start Automatically') {
          startCamera();
      } else {
          stopCamera();
      }
  });

  function startCamera() {
      fetch('/start_camera')
          .then(response => response.json())
          .then(data => {
              if (data.status === 'success') {
                  startBtn.textContent = 'Stop Camera';
                  startBtn.disabled = false;
              }
          });
  }

  function stopCamera() {
      fetch('/stop_camera')
          .then(response => response.json())
          .then(data => {
              if (data.status === 'success') {
                  startBtn.textContent = 'Start Camera';
                  startBtn.disabled = false;
              }
          });
  }

  function fetchStats() {
    fetch('/get_stats')
        .then(response => response.json())
        .then(data => {
            document.getElementById('total-detections').textContent = data.total_detections;
            document.getElementById('unique-plates').textContent = data.unique_plates;
            
            const topPlatesList = document.getElementById('top-plates');
            topPlatesList.innerHTML = data.top_plates.map(p => 
                `<li>${p.plate_number}: ${p.count} herë</li>`
            ).join('');
            
            const hourDist = document.getElementById('hour-distribution');

// Marrim zonën kohore të klientit (shfletuesit) dhe konvertojmë orët në kohën lokale
const currentTimezoneOffset = new Date().getTimezoneOffset() / 60; // Zona kohore në orë

// Krijo HTML-n për orët me detektimet
hourDist.innerHTML = data.hour_distribution.map(h => {
    // Konverto orën sipas zonës kohore
    let localHour = h.hour - currentTimezoneOffset;
    
    // Sigurohemi që ora lokale është brenda intervalit 0-23
    if (localHour < 0) localHour += 24;
    if (localHour >= 24) localHour -= 24;

    return `${localHour}:00 - ${h.count} detektime`;
}).join('<br>');

            

        });
}})