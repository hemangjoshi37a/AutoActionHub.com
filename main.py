import json
import requests
from flask import Flask, redirect, request, render_template, session
from oauthlib import oauth2
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from flask import jsonify
from config import CLIENT_ID
from config import CLIENT_SECRET
from config import your_secret_key

# CLIENT_ID = 'your google client_ID'
# CLIENT_SECRET = 'your google CLIENT_SECRET'
# your_secret_key = 'your db secret key'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = your_secret_key
app.static_folder = 'static'

db = SQLAlchemy(app)

DATA = {
    'response_type': "code",
    'redirect_uri': "https://localhost:5001/home",
    'scope': 'https://www.googleapis.com/auth/userinfo.email',
    'client_id': CLIENT_ID,
    'prompt': 'consent'
}

URL_DICT = {
    'google_oauth': 'https://accounts.google.com/o/oauth2/v2/auth',
    'token_gen': 'https://oauth2.googleapis.com/token',
    'get_user_info': 'https://www.googleapis.com/oauth2/v3/userinfo'
}

CLIENT = oauth2.WebApplicationClient(CLIENT_ID)
REQ_URI = CLIENT.prepare_request_uri(
    uri=URL_DICT['google_oauth'],
    redirect_uri=DATA['redirect_uri'],
    scope=DATA['scope'],
    prompt=DATA['prompt']
)



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    votes = db.relationship('Vote', backref='user', lazy=True)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_email = db.Column(db.Text, nullable=False)
    votes = db.relationship('Vote', backref='post', lazy=True)


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vote_type = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/', methods=['GET', 'POST'])
def index():
    code = request.args.get('code')
    if code:
        # This section handles the OAuth code to token conversion and getting user info
        token_url, headers, body = CLIENT.prepare_token_request(
            URL_DICT['token_gen'],
            authorization_response=request.url,
            redirect_url=request.base_url,
            code=code
        )
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=(CLIENT_ID, CLIENT_SECRET)
        )
        CLIENT.parse_request_body_response(json.dumps(token_response.json()))
        uri, headers, body = CLIENT.add_token(URL_DICT['get_user_info'])
        response_user_info = requests.get(uri, headers=headers, data=body)
        info = response_user_info.json()
        with app.app_context():
            user = User.query.filter_by(email=info['email']).first()
            print("User Response: ")
            print(info)
            if not user:
                user = User(email=info['email'])
                db.session.add(user)
                db.session.commit()
            session['user_id'] = user.id

    if 'user_id' not in session:
        return redirect('/login')
        
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        post = Post(title=title, content=content, user_id=user_id, user_email=user.email)
        db.session.add(post)
        db.session.commit()

    posts = Post.query.all()
    return render_template('home.html', posts=posts, user=user, current_user_email=user.email)

@app.route('/login')
def login():
    return redirect(REQ_URI)


@app.route('/home')
def home():
    code = request.args.get('code')
    token_url, headers, body = CLIENT.prepare_token_request(
        URL_DICT['token_gen'],
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(CLIENT_ID, CLIENT_SECRET)
    )
    CLIENT.parse_request_body_response(json.dumps(token_response.json()))
    uri, headers, body = CLIENT.add_token(URL_DICT['get_user_info'])
    response_user_info = requests.get(uri, headers=headers, data=body)
    info = response_user_info.json()
    with app.app_context():
        user = User.query.filter_by(email=info['email']).first()
        print("User Response: ")
        print(info)
        if not user:
            user = User(email=info['email'])
            db.session.add(user)
            db.session.commit()
        session['user_id'] = user.id
    return redirect('/')

@app.route('/get_all_post', methods=['GET', 'POST'])
def get_all_post():
    posts = Post.query.all()
    return posts


@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect('/')
    user_id = session['user_id']
    post = Post.query.get(post_id)
    # Check if the user is the author of the post
    if post.user_id == user_id:
        # Delete the post and associated votes
        Vote.query.filter_by(post_id=post_id).delete()
        db.session.delete(post)
        db.session.commit()
    return redirect('/dashboard')


@app.route('/post/<int:post_id>/upvote', methods=['POST'])
def upvote(post_id):
    if 'user_id' not in session:
        return redirect('/')
    user_id = session['user_id']
    post = Post.query.get(post_id)
    # Check if the user has already upvoted the post
    existing_vote = Vote.query.filter_by(post_id=post_id, user_id=user_id).first()
    if existing_vote:
        # If the user had previously upvoted, do nothing
        if existing_vote.vote_type == 'upvote':
            return redirect('/dashboard')
        # If the user had previously downvoted, remove the downvote
        else:
            post.downvotes -= 1
            existing_vote.vote_type = 'upvote'
    else:
        post.upvotes += 1
        vote = Vote(post_id=post_id, user_id=user_id, vote_type='upvote')
        db.session.add(vote)
    db.session.commit()
    return redirect('/dashboard')


@app.route('/post/<int:post_id>/downvote', methods=['POST'])
def downvote(post_id):
    if 'user_id' not in session:
        return redirect('/')
    user_id = session['user_id']
    post = Post.query.get(post_id)
    # Check if the user has already downvoted the post
    existing_vote = Vote.query.filter_by(post_id=post_id, user_id=user_id).first()
    if existing_vote:
        # If the user had previously downvoted, do nothing
        if existing_vote.vote_type == 'downvote':
            return redirect('/dashboard')
        # If the user had previously upvoted, remove the upvote
        else:
            post.upvotes -= 1
            existing_vote.vote_type = 'downvote'
    else:
        post.downvotes += 1
        vote = Vote(post_id=post_id, user_id=user_id, vote_type='downvote')
        db.session.add(vote)
    db.session.commit()
    return redirect('/dashboard')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/')

@app.route('/image-files')
def image_files():
    # Get the absolute path to the ./img directory
    img_dir = os.path.join(app.root_path, 'static/img')
    # Get the list of image files in the ./img directory
    image_files = os.listdir(img_dir)
    # Filter the files to include only images with the desired extensions
    image_urls = [
        '/img/' + file
        for file in image_files
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.avif'))
    ]
    return jsonify(image_urls)

@app.route('/aboutus')
def aboutus():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return render_template('aboutus.html', user=user)


@app.route('/contactus')
def contactus():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return render_template('contactus.html', user=user)

@app.route('/delete_posts_by_email/<email>', methods=['POST'])
def delete_posts_by_email(email):
    posts = Post.query.filter_by(user_email=email).all()
    for post in posts:
        Vote.query.filter_by(post_id=post.id).delete()
        db.session.delete(post)
    db.session.commit()
    return redirect('/dashboard')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001, ssl_context='adhoc')