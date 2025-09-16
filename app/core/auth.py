from fastapi import Header, HTTPException, status, Depends

def get_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != "demo":          # replace with DB / Vault lookup
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return x_api_key
