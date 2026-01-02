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

function createIndex(projectId) {
    const button = document.getElementById(`btn-index-${projectId}`);
    const originalText = button.textContent;
    
    // Show loading state
    button.textContent = '...Creating';
    button.disabled = true;
    
    fetch(`/api/create-index/${projectId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Flash success state then reload
                button.textContent = '✅ Created';
                button.classList.remove('btn-warning');
                button.classList.add('btn-success');
                setTimeout(() => location.reload(), 1000);
            } else {
                alert('Error creating index: ' + data.message);
                button.textContent = originalText;
                button.disabled = false;
            }
        })
        .catch(error => {
            console.error('Create index failed:', error);
            alert('Failed to create index. Check console for details.');
            button.textContent = originalText;
            button.disabled = false;
        });
}

function filterMissingIndexes() {
    const cards = document.querySelectorAll('.project-card');
    const metric = document.querySelector('.compliance-metric');
    const isFiltered = metric.classList.contains('filtered');
    
    cards.forEach(card => {
        const hasIndex = card.querySelector('.index-badge.valid') !== null;
        if (isFiltered) {
            card.style.display = 'block';
        } else {
            card.style.display = hasIndex ? 'none' : 'block';
        }
    });
    
    if (isFiltered) {
        metric.classList.remove('filtered');
        metric.style.background = 'rgba(0, 0, 0, 0.2)';
    } else {
        metric.classList.add('filtered');
        metric.style.background = 'rgba(255, 167, 38, 0.2)';
    }
}

async function fixFrontmatter(projectId) {
    const btn = document.getElementById(`btn-fix-${projectId}`);
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Fixing...';
    
    try {
        const response = await fetch(`/api/fix-frontmatter/${projectId}`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            btn.textContent = '✓ Fixed';
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-success');
            setTimeout(() => location.reload(), 1000);
        } else {
            btn.textContent = `Failed: ${data.error}`;
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 3000);
        }
    } catch (e) {
        console.error('Fix frontmatter failed:', e);
        btn.textContent = 'Error';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
        }, 3000);
    }
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

