#!/usr/bin/env python3
"""
TEE + NEAR AI Agent Reference Implementation

This file demonstrates the patterns discussed in the technical blog:
"Trusted Execution Environments and NEAR AI: A Technical Deep Dive"

Note: This is a reference implementation for educational purposes.
Actual TEE integration requires specific hardware SDKs (Intel SGX, etc.
"""

import os
import json
import time
import hashlib
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AttestationReport:
    """Simulated attestation report."""
    enclave_hash: str
    timestamp: float
    signature: str
    report_data: str

    def to_dict(self) -> dict:
        return asdict(self)


class MockEnclave:
    """
    Mock TEE Enclave for demonstration.

    In production, this would interface with actual TEE hardware:
    - Intel SGX SDK
    - Azure Confidential Computing
    - AWS Nitro Enclaves
    """

    def __init__(self, enclave_id: str = "demo-enclave"):
        self.enclave_id = enclave_id
        self.enclave_hash = self._generate_enclave_hash()
        self.sealed_data: Dict[str, bytes] = {}

        # Simulate sealed private key storage
        self._init_sealed_keys()

    def _generate_enclave_hash(self) -> str:
        """Generate mock enclave measurement (MRENCLAVE)."""
        return hashlib.sha256(f"enclave-code-{self.enclave_id}".encode()).hexdigest()

    def _init_sealed_keys(self):
        """Initialize sealed private key storage."""
        # In real TEE, this would be hardware-sealed storage
        private_key = ed25519.Ed25519PrivateKey.generate()
        self.sealed_data["private_key"] = private_key.private_bytes_raw()

    def get_private_key(self) -> ed25519.Ed25519PrivateKey:
        """Get sealed private key from enclave."""
        key_bytes = self.sealed_data.get("private_key")
        if key_bytes:
            return ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)
        return ed25519.Ed25519PrivateKey.generate()

    def seal(self, data: str) -> str:
        """
        Seal data to the enclave.

        In production: uses SGX sealing keys or similar
        """
        sealed = hashlib.sha256(f"{self.enclave_id}:{data}".encode()).hexdigest()
        return f"sealed:{sealed[:32]}:{data[:16]}..."

    def unseal(self, sealed_data: str) -> Optional[str]:
        """Unseal data from enclave storage."""
        if sealed_data.startswith("sealed:"):
            return "original_data"
        return None

    def sign(self, message: str) -> str:
        """Sign message within enclave."""
        private_key = self.get_private_key()
        signature = private_key.sign(message.encode())
        return signature.hex()

    def remote_attestation(self) -> AttestationReport:
        """
        Generate remote attestation report.

        In production, this would call actual IAS (Intel Attestation Service)
        or equivalent cloud attestation service.
        """
        report_data = json.dumps({
            "enclave_id": self.enclave_id,
            "timestamp": time.time()
        })

        signature = self.sign(report_data)

        return AttestationReport(
            enclave_hash=self.enclave_hash,
            timestamp=time.time(),
            signature=signature,
            report_data=report_data
        )

    def verify_attestation(self) -> bool:
        """Verify enclave attestation (self-check)."""
        report = self.remote_attestation()
        return report.enclave_hash == self.enclave_hash


class TEENearAgent:
    """
    NEAR AI Agent with TEE protection.

    This agent demonstrates:
    1. Private keys stored in enclave
    2. All signing operations within enclave
    3. Remote attestation for trust verification
    """

    def __init__(
        self,
        api_key: str,
        wallet_secret: Optional[str] = None,
        use_tee: bool = True
    ):
        self.api_key = api_key
        self.use_tee = use_tee

        # Initialize TEE enclave
        if use_tee:
            self.enclave = MockEnclave()
            logger.info(f"TEE Agent initialized with enclave: {self.enclave.enclave_hash[:16]}...")
        else:
            self.enclave = None
            logger.warning("Running in non-TEE mode (less secure)")

        # Load wallet
        if wallet_secret:
            self.wallet_secret = wallet_secret
        else:
            self.wallet_secret = os.getenv("NEAR_WALLET_PRIVATE_KEY")

    def verify_enclave(self) -> bool:
        """Verify enclave attestation before operations."""
        if not self.enclave:
            return False

        attestation = self.enclave.remote_attestation()
        logger.info(f"Attestation: {attestation.enclave_hash[:16]}...")

        # In production, verify against IAS or attestation service
        return self.enclave.verify_attestation()

    def place_bid(
        self,
        job_id: str,
        amount: float,
        proposal: str,
        eta_seconds: int = 3600
    ) -> dict:
        """Place bid on NEAR AI job through TEE."""

        if self.use_tee and not self.verify_enclave():
            raise ValueError("Enclave attestation failed!")

        # Prepare bid data
        bid_data = json.dumps({
            "job_id": job_id,
            "amount": str(amount),
            "proposal": proposal,
            "timestamp": time.time()
        })

        # Sign within enclave if available
        if self.enclave:
            signature = self.enclave.sign(bid_data)
            attestation = self.enclave.remote_attestation().to_dict()
        else:
            # Non-TEE fallback (less secure)
            signature = hashlib.sha256(f"{bid_data}{self.wallet_secret}".encode()).hexdigest()
            attestation = {}

        # Submit to NEAR AI
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "amount": str(amount),
            "eta_seconds": eta_seconds,
            "proposal": proposal,
            "signature": signature,
            "attestation": attestation
        }

        try:
            response = requests.post(
                f"https://market.near.ai/v1/jobs/{job_id}/bids",
                headers=headers,
                json=payload,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Bid placed successfully: {job_id}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to place bid: {e}")
            return {"error": str(e)}

    def submit_deliverable(
        self,
        job_id: str,
        deliverable: str,
        deliverable_hash: Optional[str] = None
    ) -> dict:
        """Submit job deliverable through TEE."""

        if self.use_tee and not self.verify_enclave():
            raise ValueError("Enclave attestation failed!")

        # Seal deliverable in enclave
        if self.enclave:
            sealed_deliverable = self.enclave.seal(deliverable)
        else:
            sealed_deliverable = deliverable

        # Calculate hash
        if not deliverable_hash:
            deliverable_hash = hashlib.sha256(deliverable.encode()).hexdigest()

        # Sign submission
        submit_data = json.dumps({
            "job_id": job_id,
            "deliverable": sealed_deliverable,
            "hash": deliverable_hash,
            "timestamp": time.time()
        })

        signature = self.enclave.sign(submit_data) if self.enclave else hashlib.sha256(
            f"{submit_data}{self.wallet_secret}".encode()
        ).hexdigest()

        # Submit to NEAR AI
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "deliverable": deliverable,
            "deliverable_hash": f"sha256:{deliverable_hash}",
            "signature": signature
        }

        try:
            response = requests.post(
                f"https://market.near.ai/v1/jobs/{job_id}/submit",
                headers=headers,
                json=payload,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Deliverable submitted: {job_id}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to submit deliverable: {e}")
            return {"error": str(e)}


class AttestationVerifier:
    """
    Verify TEE attestation reports.

    In production, this would interface with:
    - Intel Attestation Service (IAS)
    - Azure Attestation Service
    - AWS Nitro Enclaves Attestation
    """

    def __init__(self, trusted_measurements: List[str]):
        """
        Initialize with trusted enclave measurements.

        Args:
            trusted_measurements: List of approved enclave hashes (MRENCLAVE)
        """
        self.trusted_measurements = set(trusted_measurements)

    def verify(self, attestation: AttestationReport) -> bool:
        """
        Verify an attestation report.

        Checks:
        1. Enclave measurement is trusted
        2. Signature is valid (non-empty for demo)
        3. Report is fresh (not replayed)
        """
        # 1. Check measurement
        if attestation.enclave_hash not in self.trusted_measurements:
            logger.warning(f"Untrusted enclave: {attestation.enclave_hash}")
            return False

        # 2. Check freshness (5 minute window)
        age = time.time() - attestation.timestamp
        if age > 300:
            logger.warning(f"Stale attestation: {age:.0f}s old")
            return False

        # 3. Verify signature exists (simplified for demo)
        # In production, this would use the actual public key verification
        if not attestation.signature or len(attestation.signature) < 32:
            logger.warning("Invalid signature")
            return False

        logger.info("Attestation verified!")
        return True


def demo_tee_agent():
    """Demonstrate TEE-protected NEAR AI agent."""

    print("=" * 60)
    print("TEE + NEAR AI Agent Demo")
    print("=" * 60)

    # Initialize agent with TEE
    print("\n1. Initializing TEE Agent...")
    agent = TEENearAgent(
        api_key="demo_key",
        use_tee=True
    )

    # Verify enclave
    print("\n2. Verifying Enclave Attestation...")
    if agent.verify_enclave():
        print("   ✅ Enclave attestation verified!")
    else:
        print("   ❌ Attestation failed!")
        return

    # Simulate placing a bid
    print("\n3. Simulating Bid Placement...")
    print("   Job ID: demo-job-123")
    print("   Amount: 2.5 NEAR")
    print("   Proposal: AI-generated proposal text...")

    # Note: Won't actually call API without valid key
    print("\n   ✅ Bid would be signed in enclave")
    print(f"   Signature: {agent.enclave.sign('demo-bid')[:32]}...")

    # Simulate deliverable submission
    print("\n4. Simulating Deliverable Submission...")
    deliverable = """
# Demo Deliverable

This is a sample deliverable generated by the TEE-protected agent.

## Content

- Analysis completed
- Results compiled
- Documentation provided
"""
    sealed = agent.enclave.seal(deliverable)
    print(f"   Sealed deliverable: {sealed}")

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


def demo_attestation_verification():
    """Demonstrate attestation verification."""

    print("\n" + "=" * 60)
    print("Attestation Verification Demo")
    print("=" * 60)

    # Create enclave
    enclave = MockEnclave()
    print(f"\nEnclave hash: {enclave.enclave_hash[:32]}...")

    # Generate attestation
    print("\nGenerating attestation report...")
    attestation = enclave.remote_attestation()
    print(f"Report timestamp: {datetime.fromtimestamp(attestation.timestamp)}")
    print(f"Signature: {attestation.signature[:32]}...")

    # Verify with trusted verifier
    print("\nVerifying attestation...")
    verifier = AttestationVerifier(trusted_measurements=[enclave.enclave_hash])

    if verifier.verify(attestation):
        print("✅ Attestation is valid!")
    else:
        print("❌ Attestation verification failed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        demo_attestation_verification()
    else:
        demo_tee_agent()
        demo_attestation_verification()
