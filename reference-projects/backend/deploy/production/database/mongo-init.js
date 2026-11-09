const appUser = process.env.MONGO_APP_USER;
const appPassword = process.env.MONGO_APP_PASSWORD;

if (!appUser || !appPassword) {
  throw new Error("MONGO_APP_USER and MONGO_APP_PASSWORD are required");
}

db = db.getSiblingDB("plat");
db.createUser({
  user: appUser,
  pwd: appPassword,
  roles: [
    { role: "readWrite", db: "plat" },
    { role: "readWrite", db: "user" },
    { role: "readWrite", db: "trash" },
  ],
});

