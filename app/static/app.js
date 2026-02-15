// Global utility functions for Van List 2026

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
}

// Redirect to login on 401 from any fetch
const originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await originalFetch.apply(this, args);
    if (response.status === 401 && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
    }
    return response;
};
