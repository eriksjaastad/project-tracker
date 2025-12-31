// Project Tracker Dashboard JavaScript

function refreshData() {
    const button = document.querySelector('.btn-refresh');
    const originalText = button.textContent;
    
    // Show loading state
    button.textContent = '⟳ Refreshing...';
    button.disabled = true;
    
    fetch('/api/refresh', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Reload page to show updated data
                location.reload();
            } else {
                alert('Error refreshing data: ' + data.message);
                button.textContent = originalText;
                button.disabled = false;
            }
        })
        .catch(error => {
            console.error('Refresh failed:', error);
            alert('Failed to refresh data. Check console for details.');
            button.textContent = originalText;
            button.disabled = false;
        });
}

// Format timestamps on page load
document.addEventListener('DOMContentLoaded', function() {
    // Any client-side initialization can go here
    console.log('Project Tracker Dashboard loaded');
});

// Toggle alert visibility by severity
function toggleAlerts(severity) {
    const alerts = document.querySelectorAll(`.alert-${severity}`);
    const toggle = document.getElementById(`toggle-${severity}`);
    
    // Check if alerts are currently visible
    const isVisible = alerts[0] && alerts[0].style.display !== 'none';
    
    // Toggle visibility
    alerts.forEach(alert => {
        alert.style.display = isVisible ? 'none' : 'block';
    });
    
    // Update toggle link style
    if (isVisible) {
        toggle.style.opacity = '0.5';
        toggle.style.textDecoration = 'line-through';
    } else {
        toggle.style.opacity = '1';
        toggle.style.textDecoration = 'none';
    }
}

