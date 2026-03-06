// Sidebar toggle for mobile
(function() {
	var burger = document.getElementById('sidebar-burger');
	var sidebar = document.getElementById('sidebar');
	var overlay = document.getElementById('sidebar-overlay');

	if (!burger || !sidebar || !overlay) return;

	function openSidebar() {
		sidebar.classList.add('open');
		overlay.classList.add('open');
	}

	function closeSidebar() {
		sidebar.classList.remove('open');
		overlay.classList.remove('open');
	}

	// Expose globally so action buttons can close sidebar on mobile
	window.closeSidebarOnMobile = function() {
		if (window.innerWidth <= 768) {
			closeSidebar();
		}
	};

	burger.addEventListener('click', function() {
		if (sidebar.classList.contains('open')) {
			closeSidebar();
		} else {
			openSidebar();
		}
	});

	overlay.addEventListener('click', closeSidebar);
})();
