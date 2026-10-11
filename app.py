from flask import Flask, render_template, request, redirect, session, send_file
from flask_sqlalchemy import SQLAlchemy
import os
from io import BytesIO

app = Flask(__name__)

app.secret_key = "my_secret_key"

db_path = os.path.join(app.root_path, "project.db")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Users(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)

    files = db.relationship("UserFile", backref="user", lazy=True, cascade="all, delete-orphan")
    folders = db.relationship("Folder", backref="user", lazy=True, cascade="all, delete-orphan")


class Folder(db.Model):
    __tablename__ = "folders"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)


class UserFile(db.Model):
    __tablename__ = "user_files"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_data = db.Column(db.LargeBinary, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)


with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = Users.query.filter_by(username=username).first()

        if user and user.password_hash == password:
            session["username"] = user.username
            session["user_id"] = user.id
            return redirect("/files")

        return render_template("login.html", error="Wrong username or password")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return render_template("register.html", error="Please fill in all fields")

        existing_user = Users.query.filter_by(username=username).first()

        if existing_user:
            return render_template("register.html", error="Username already exists")

        new_user = Users(
            username=username,
            password_hash=password
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect("/login")

    return render_template("register.html")


@app.route("/files")
def files():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    folder_id = request.args.get("folder_id", type=int)

    current_folder = None
    if folder_id:
        current_folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first_or_404()

    folders = Folder.query.filter_by(user_id=user_id, parent_id=folder_id).all()
    user_files = UserFile.query.filter_by(user_id=user_id, folder_id=folder_id).all()

    return render_template(
        "files.html",
        folders=folders,
        files=user_files,
        current_folder=current_folder,
        folder_id=folder_id,
        username=session["username"]
    )


@app.route("/folder/create", methods=["POST"])
def create_folder():
    if "user_id" not in session:
        return redirect("/login")

    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id", type=int)

    if not name:
        return redirect("/files" + ("?folder_id=" + str(parent_id) if parent_id else ""))

    if parent_id:
        parent = Folder.query.filter_by(id=parent_id, user_id=session["user_id"]).first()
        if not parent:
            return redirect("/files")

    new_folder = Folder(name=name, user_id=session["user_id"], parent_id=parent_id)
    db.session.add(new_folder)
    db.session.commit()

    return redirect("/files" + ("?folder_id=" + str(parent_id) if parent_id else ""))


@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")

    file = request.files.get("file")
    folder_id = request.form.get("folder_id", type=int)

    if not file or file.filename == "":
        return redirect("/files" + ("?folder_id=" + str(folder_id) if folder_id else ""))

    if folder_id:
        folder = Folder.query.filter_by(id=folder_id, user_id=session["user_id"]).first()
        if not folder:
            return redirect("/files")

    new_file = UserFile(
        filename=file.filename,
        file_data=file.read(),
        user_id=session["user_id"],
        folder_id=folder_id
    )

    db.session.add(new_file)
    db.session.commit()

    return redirect("/files" + ("?folder_id=" + str(folder_id) if folder_id else ""))


@app.route("/download/<int:file_id>")
def download(file_id):
    if "user_id" not in session:
        return redirect("/login")

    user_file = UserFile.query.filter_by(id=file_id, user_id=session["user_id"]).first_or_404()

    return send_file(
        BytesIO(user_file.file_data),
        download_name=user_file.filename,
        as_attachment=True
    )


@app.route("/delete/<int:file_id>", methods=["POST"])
def delete(file_id):
    if "user_id" not in session:
        return redirect("/login")

    user_file = UserFile.query.filter_by(id=file_id, user_id=session["user_id"]).first_or_404()
    folder_id = user_file.folder_id

    db.session.delete(user_file)
    db.session.commit()

    return redirect("/files" + ("?folder_id=" + str(folder_id) if folder_id else ""))


@app.route("/folder/delete/<int:folder_id>", methods=["POST"])
def delete_folder(folder_id):
    if "user_id" not in session:
        return redirect("/login")

    folder = Folder.query.filter_by(id=folder_id, user_id=session["user_id"]).first_or_404()
    parent_id = folder.parent_id

    child_folders = Folder.query.filter_by(user_id=session["user_id"], parent_id=folder.id).all()
    child_files = UserFile.query.filter_by(user_id=session["user_id"], folder_id=folder.id).all()

    for child_file in child_files:
        db.session.delete(child_file)

    for child_folder in child_folders:
        db.session.delete(child_folder)

    db.session.delete(folder)
    db.session.commit()

    return redirect("/files" + ("?folder_id=" + str(parent_id) if parent_id else ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)
