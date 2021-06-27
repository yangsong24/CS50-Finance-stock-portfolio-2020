import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timezone
from helpers import apology, login_required, lookup, usd
import re

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    result = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    cash = result[0]['cash']



    # pull all transactions belonging to user
    portfolio = db.execute("SELECT stock, quantity FROM portfolio WHERE user_id = :user_id GROUP BY stock", user_id=session["user_id"])



    grand_total = cash

    # determine current price, stock total value and grand total value
    for stock in portfolio:
        price = lookup(stock['stock'])['price']
        total = stock['quantity'] * price
        stock.update({'price': usd(price), 'total': usd(total)})
        grand_total += total


    return render_template("index.html", stocks=portfolio, cash= usd(cash), total= usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # ensure stock symbol and number of shares was submitted
        if (not request.form.get("symbol")) or (not request.form.get("shares")):
            return apology("must provide stock symbol and number of shares")

        # ensure number of shares is valid
        if int(request.form.get("shares")) <= 0:
            return apology("must provide valid number of shares (integer)")

        # pull quote from yahoo finance
        quote = lookup(request.form.get("symbol"))

        # check if valid stock name provided
        if quote == None:
            return apology("Stock symbol not valid, please try again")

        # cost of transaction
        cost = int(request.form.get("shares")) * quote['price']

        # check if user has enough cash
        result = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        if cost > result[0]["cash"]:
            return apology("you do not have enough cash for this transaction")

        # update cash amount in users database
        db.execute("UPDATE users SET cash=cash-:cost WHERE id=:id", cost=cost, id=session["user_id"]);

        # add transaction to transaction database
        add_transaction = db.execute("INSERT INTO transactions (user_id, stock, quantity, price, date) VALUES (:user_id, :stock, :quantity, :price, :date)",
                          user_id=session["user_id"], stock=quote["symbol"], quantity=int(request.form.get("shares")), price=quote['price'], date=datetime.now(tz=None).strftime("%Y-%m-%d %H:%M:%S"))

        # pull number of shares of symbol in portfolio
        curr_portfolio = db.execute("SELECT quantity FROM portfolio WHERE user_id=:user_id and stock=:stock",
                user_id=session["user_id"], stock=quote["symbol"])

        # add to portfolio database
        # if symbol is new, add to portfolio
        if not curr_portfolio:
            db.execute("INSERT INTO portfolio (user_id, stock, quantity) VALUES (:user_id, :stock, :quantity)",
                user_id=session["user_id"], stock=quote["symbol"], quantity=int(request.form.get("shares")))

        # if symbol is already in portfolio, update quantity of shares and total
        else:
            db.execute("UPDATE portfolio SET quantity=quantity+:quantity WHERE user_id=:user_id and stock=:stock",
                quantity=int(request.form.get("shares")), user_id=session["user_id"], stock=quote["symbol"]);

        return redirect("/")


    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

     # pull all transactions belonging to user
    portfolio = db.execute("SELECT stock, quantity, price, date FROM transactions WHERE user_id=:id", id=session["user_id"])

    if not portfolio:
        return apology("sorry you have no transactions")

    return render_template("history.html", stocks=portfolio)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")


    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol")


        quote = lookup(request.form.get("symbol"))


        if quote == None:
            return apology("Stock symbol not valid, please try again")


        else:
            return render_template("quoted.html", symbol=quote["symbol"], name=quote["name"], price=quote["price"])


    else:
         return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

            # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide password", 403)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and password confirmation must match")

        password = request.form.get("password")


        if len(password) < 8:
                return apology("Make sure your password is at lest 8 letters")
        elif re.search('[0-9]',password) is None:
                return apology("Make sure your password has a number in it")
        elif re.search('[A-Z]',password) is None:
                return apology("Make sure your password has a capital letter in it")


        hash =  generate_password_hash(request.form.get("password"))

        register_user = db.execute("INSERT INTO users (username,hash) VALUES (:username, :hash)", username=request.form.get("username"), hash=hash)

        if not register_user:
            return apology("usernsme already registered", 400)


        session["user_id"] = register_user


        return redirect("/")


    else:
         return render_template("register.html")





@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

# if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure stock symbol and number of shares was submitted
        if (not request.form.get("stock")) or (not request.form.get("shares")):
            return apology("must provide stock symbol and number of shares")

        # ensure number of shares is valid
        if int(request.form.get("shares")) <= 0:
            return apology("must provide valid number of shares (integer)")

        quantity = request.form.get("shares")
        available = db.execute("SELECT quantity FROM portfolio WHERE user_id=:user_id and :stock=stock", user_id=session["user_id"], stock=request.form.get("stock"))[0]["quantity"]

        # check that number of shares being sold does not exceed quantity in portfolio
        if int(request.form.get("shares")) > available:
            return apology("You may not sell more shares than you currently hold")


        # pull quote from yahoo finance
        quote = lookup(request.form.get("stock"))
        av_shares = available - int(quantity)
        # check is valid stock name provided
        if quote == None:
            return apology("Stock symbol not valid, please try again")

        # calculate cost of transaction
        cost = int(request.form.get("shares")) * quote['price']

        # update cash amount in users database
        db.execute("UPDATE users SET cash=cash+:cost WHERE id=:id", cost=cost, id=session["user_id"]);

        # add transaction to transaction database
        add_transaction = db.execute("INSERT INTO transactions (user_id, stock, quantity, price, date) VALUES (:user_id, :stock, :quantity, :price, :date)",
            user_id=session["user_id"], stock=quote["symbol"], quantity=int(request.form.get("shares")), price=quote['price'], date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # update quantity of shares and total


        if int(av_shares) == 0:
            db.execute("DELETE FROM portfolio WHERE user_id=:user_id and stock=:stock",
                user_id=session["user_id"], stock=quote["symbol"]);

        elif int(av_shares) > 0:
             db.execute("UPDATE portfolio SET quantity=quantity-:quantity WHERE user_id=:user_id and stock=:stock",
            quantity=int(request.form.get("shares")), user_id=session["user_id"], stock=quote["symbol"]);

        return redirect("/")


    else:
        # pull all transactions belonging to user
        portfolio = db.execute("SELECT stock FROM portfolio")

        return render_template("sell.html", stocks=portfolio)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)



