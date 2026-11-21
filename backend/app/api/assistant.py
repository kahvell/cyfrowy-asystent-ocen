from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.ai.pipelines import legal_qa
from app.ai.rag import retrieve
from app.db import get_session
from app.models import User
from app.security import get_current_user

router = APIRouter(tags=["assistant"])


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@router.post("/assistant/legal-qa")
def ask(body: QuestionIn, _: User = Depends(get_current_user), session: Session = Depends(get_session)):
    hits = retrieve(session, body.question, k=5)
    chunks = [{"ref": h.ref, "text": h.text, "source": h.source} for h in hits]
    res = legal_qa(body.question, chunks)
    cited = set(res.data.citations)
    return {
        "answer": res.data.answer,
        "citations": [c for c in chunks if c["ref"] in cited] or chunks[:2],
        "model": res.model,
        "prompt_version": res.prompt_version,
    }
