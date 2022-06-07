.. _galacteek-glossary:


==========
 Glossary
==========


.. glossary::

    CID
        
        IPFS Content IDentifier.
        
        Identifies content in IPFS. There are two versions
        of identifiers: CIDv0 (in base58) and CIDv1 (can be represented
        in base58 or base32).
        
        CIDv0 examples (will always start with *Qm*)::

            QmZGqE15BKQqrm6ADmnRyBLQSF1Ht16T9GSmp88vFxZ1Nu
            QmUvdbNn65yvkxoGU3FBNbZWEpvR72LGiVAY15LYKRkY6k

        CIDv1 examples::

            zdj7WZ4rubKSt8YvKkLRg92HMU3X7HBhdM7p8azhuyTbe1zrG
            bafybeidhx5nzmk4n7vj24wjbyx5lcvrxjdrrt5gg7rejzydfixqlwx7ae4

    CIDv0

        IPFS Content IDentifier (version 0)

        Version 0 Content IDentifiers are just multihashes
        (see :term:`multihash`) and do not have a multibase, as opposed
        to version 1 CIDs. Their string representation is always
        encoded in base 58.

    CIDv1

        IPFS Content IDentifier (version 1)

        CIDv1 differs from CIDv0 and introduces explicit encoding of 
        the CID version and the IPLD format::

            <cid-version><ipld-format><multihash>

        Their string representation can be encoded in different bases
        (base58, base32, etc..), see :term:`multibase`

    CID upgrade

        The process of converting/upgrading a :term:`CIDv0` (CID version 0)
        to a :term:`CIDv1` (CID version 1)

    DAG

        Directed Acyclic Graph. From Wikipedia:

            In mathematics and computer science, a directed acyclic graph
            (DAG /ˈdæɡ/), is a finite directed graph with no directed cycles. 

            DAGs can model many different kinds of information.

    DID

        Decentralized Identifier.

        The W3C defines DIDs precisely in the DID spec:

            Decentralized Identifiers (DIDs) are a new type of identifier
            for verifiable, decentralized digital identity. These new
            identifiers are designed to enable the controller of a DID
            to prove control over it and to be implemented independently of
            any centralized registry, identity provider, or certificate
            authority. DIDs are URLs that relate a DID subject to means
            for trustable interactions with that subject. DIDs resolve
            to DID Documents — simple documents that describe how to use
            that specific DID. Each DID Document may express cryptographic
            material, verification methods, and/or service endpoints.
            These provide a set of mechanisms which enable a DID controller
            to prove control of the DID. Service endpoints enable trusted
            interactions with the DID subject.

    dweb

        The distributed web

    DHT
    
        Distributed Hash Table

        From Wikipedia:

            A distributed hash table (DHT) is a class of a decentralized
            distributed system that provides a lookup service similar to a
            hash table: (key, value) pairs are stored in a DHT, and any
            participating node can efficiently retrieve the value associated
            with a given key

    ENS

        Ethereum Name Service

        ENS_

    garbage collector

        The job of the IPFS garbage collector is to
        routinely purge unneeded/obsolete objects from
        the IPFS objects repository.

    galacteek

        Browser and content crafter for the distributed web

    go-ipfs

        IPFS daemon implementation in Go

    IPFS

        InterPlanetary File System

        IPFS_

    IPFS path

        An IPFS path is a full path to an IPFS object. Examples::

            /ipfs/bafybeid534xc5jnyi4vgndvw7ngq72q7iadkloqyb5anh34ia7z3k32tw4/galacteek.png
            /ipns/ipfs.io

        :term:`galacteek` uses full IPFS paths wherever possible to
        reference objects.

    IPNS

        InterPlanetary Name System:

            IPNS is a PKI namespace, where names are the hashes of
            public keys, and the private key enables publishing new
            (signed) values. In both publish and resolve, the default
            name used is the node's own PeerID, which is the hash of
            its public key.

    js-ipfs

        IPFS implementation in Javascript

    Merkle tree

        In cryptography and computer science, a hash tree or Merkle tree is
        a tree in which every non-leaf node is labelled with the cryptographic
        hash of the labels or values (in case of leaves) of its child nodes.
        Hash trees allow efficient and secure verification of the contents of
        large data structures. Hash trees are a generalization of hash lists
        and hash chains.

    MFS

        Mutable filesystem

        The Mutable Filesystem is an IPFS feature that gives the
        ability to manipulate IPFS objects as if they were part
        of a unix filesystem . This is used by the filemanager.

    Multibase

        Self-describing base encodings.

        multiformats_

    Multiformats

        Excerpt from the project page:

            The Multiformats Project is a collection of protocols which aim to
            future-proof systems, today. They do this mainly by enhancing format
            values with self-description. This allows interoperability, protocol
            agility, and helps us avoid lock in.

    Multihash

        Self-describing hash.

        A multihash encodes the hash function type, the length of the digest,
        and the digest value (the actual hash). Their format is::

            <hash-func-type><digest-length><digest-value>

        multiformats_

    Node

        Your IPFS node (an agent/node in the IPFS Peer-to-Peer
        network)

    pinning

        The act (and choice/duty) of pinning some content,
        refers to the 

    RDF
        Resource Description Framework

        RDF is a standard model for data interchange on the Web.
        RDF has features that facilitate data merging even if the
        underlying schemas differ, and it specifically supports the
        evolution of schemas over time without requiring all the data
        consumers to be changed.

    RPS

        Remote Pinning Service

        A Remote Pinning Service is an IPFS service that pins
        content on demand, through a specific API. go-ipfs
        supports remote pinning since the 0.8.0 version.

    UnixFS

        UnixFS is a protocol-buffers-based format for describing files,
        directories, and symlinks in IPFS. This data format is used to
        represent files and all their links and metadata in IPFS. UnixFS
        creates a block (or a tree of blocks) of linked objects.

        See the unixfs_ documentation


.. _IPFS: ipns://ipfs.io
.. _ENS: https://ens.domains/
.. _multiformats: https://multiformats.io
.. _unixfs:  https://docs.ipfs.io/concepts/file-systems/#unix-file-system-unixfs
