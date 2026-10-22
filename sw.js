self.addEventListener("push", function(event) {
    const data = event.data ? event.data.json() : {};

    const options = {
        body: data.body || "You have a new notification.",
        icon: "/static/icon.png",
        badge: "/static/icon.png"
    };

    event.waitUntil(
        self.registration.showNotification(
            data.title || "Grocery Food Manager",
            options
        )
    );
});