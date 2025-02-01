Authentication is possible as well!

Usually as per rasa http documentation...rasa admin user has access to all endpoints...but you can use a user as well.

```python
def _generate_jwt_token(self) -> str:
    """Generate a JWT token for authentication."""
    if not self.jwt_secret:
        raise RasaClientError("JWT secret not configured")
        
    payload = {
        "user": {
            "username": self.sender_id,
            # Changed from 'user' to 'admin' to get proper permissions
            "role": "admin"  
        }
    }
    return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
```

To use this:

1. Start Rasa with the JWT secret:
```bash
rasa run --enable-api --jwt-secret your_jwt_secret
```

2. Run the Python client with the same secret:
```python
async def main() -> None:
    # Make sure this matches the secret used to start Rasa
    jwt_secret = "your_jwt_secret"  
    
    try:
        client = await RasaClient.create(jwt_secret=jwt_secret)
        # Rest of the code...
```

Alternatively, if you want to keep using "user" as the role, you can set the environment variable before starting Rasa:

```bash
# Set this before starting Rasa
export RASA_JWT_ADMIN_ROLES="user,admin,rasa"

# Then start Rasa
rasa run --enable-api --jwt-secret your_jwt_secret
```

Which approach would you prefer to use? I can help you implement either one.

You can cURL it as well to see auth is working:

Use an Admin Role in Your Token
Include a role claim (e.g. "role": "admin") that matches the default admin roles. For instance:

Generate a token with "role": "admin"

```bash
TOKEN=$(python -c "
import jwt, os
print(jwt.encode(
    {'user': {'username': 'ehzawad', 'role': 'admin'}}, 
    os.environ['JWT_SECRET'], 
    algorithm='HS256'
))
")
```

This typically succeeds unless you have also configured Rasa to look for custom admin roles.

```bash
export RASA_JWT_ADMIN_ROLES="user,admin,rasa"
curl -H "Authorization: Bearer $TOKEN" http://localhost:5005/status
```
you can use openssl to generate a random jwt-secret using 
```bash
openssl rand -hex 4
```

Make sure to run rasa with your jwt secrect

```bash
rasa run --enable-api --cors "*" --jwt-secret 62633a21
```

you may need to export 'em (all necessay env variables) in the environment or keep it in the .env file

```bash
export JWT_SECRET="62633a21"
```

If inside .env file in the project directory..
then use this command to export 'em

```bash
export $(grep -v '^#' .env | xargs)
```

I have not incorporated it in the code to keep this repo simple.
